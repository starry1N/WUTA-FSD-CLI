"""File mailbox for the existing Manager worker; callbacks never run business logic."""
import hashlib
import json
from pathlib import Path
import threading
import time
import uuid

from config_store import ConfigStore, atomic_json


def valid_id(value):
    return isinstance(value, str) and len(value) == 32 and all(c in '0123456789abcdef' for c in value)


class ControlAPI:
    def __init__(self, manager, root):
        self.manager = manager
        self.root = Path(root)
        self.directory = self.root / '.runtime/fsd_manager/control'
        self.inbox, self.results = self.directory / 'inbox', self.directory / 'results'
        self.inbox.mkdir(parents=True, exist_ok=True)
        self.results.mkdir(parents=True, exist_ok=True)
        self.boot = uuid.uuid4().hex
        self.active = None
        self.last = None
        self.snapshot = {}
        self.stopping = threading.Event()
        self.thread = None
        self.store, self.config_error = None, None
        try:
            self.store = ConfigStore(root, manager.options)
        except Exception as exc:
            self.config_error = str(exc)

    def start(self):
        self.thread = threading.Thread(target=self.heartbeat, daemon=True)
        self.thread.start()

    def state(self):
        return {'boot': self.boot, 'active': self.active, 'last': self.last,
                'config_error': self.config_error}

    def heartbeat(self):
        while not self.stopping.is_set():
            try:
                atomic_json(self.directory / 'heartbeat.json', {
                    **self.snapshot, **self.state(), 'online': True,
                    'updated_ns': str(time.time_ns())})
            except OSError:
                pass  # Radio reports a stale heartbeat; Manager remains usable locally.
            self.stopping.wait(1)

    def close(self):
        self.stopping.set()
        if self.thread:
            self.thread.join(timeout=2)
        try:
            atomic_json(self.directory / 'heartbeat.json', {
                **self.snapshot, **self.state(), 'online': False,
                'updated_ns': str(time.time_ns())})
        except OSError:
            pass  # Never prevent Manager cleanup if its runtime directory disappeared.

    def submit(self, operation, **arguments):
        if operation == 'cli.cycle_mode':
            arguments.setdefault('expected_mode', self.snapshot.get('selected_mode'))
        if len(list(self.inbox.glob('*.json'))) >= 32:
            raise ValueError('CLI mailbox is full')
        request = {'id': uuid.uuid4().hex, 'boot': self.boot, 'op': operation,
                   'expires_ns': str(time.time_ns() + 180_000_000_000),
                   'source_stamp_ns': str(time.time_ns()), **arguments}
        atomic_json(self.inbox / (request['id'] + '.json'), request)
        return request['id']

    def status(self):
        m = self.manager
        return {**self.state(), 'phase': m.phase,
                'selected_mode': self.snapshot.get('selected_mode'),
                'active_mode': self.snapshot.get('active_mode'),
                'runtime_exit_code': m.runtime_exit_code,
                'running': bool(m.child and m.child.poll() is None),
                'run': (m.radio_run or {}).get('scope'),
                'checks': {key: {'ok': value['ok'], 'status': value.get('status'),
                                 'detail': str(value.get('detail', ''))[-600:]}
                           for key, value in m.results.items()}}

    def execute(self, request):
        op = request['op']
        if op == 'cli.status':
            return self.status()
        if op == 'cli.result':
            if not valid_id(request.get('request_id')):
                raise ValueError('Invalid result identity')
            path = self.results / (request['request_id'] + '.json')
            return json.loads(path.read_text(encoding='utf-8'))
        if request.get('boot') != self.boot:
            raise ValueError('CLI已重启；请等待新状态后重新操作')
        if op in ('cli.check', 'cli.start', 'cli.stop', 'cli.cycle_mode'):
            if op == 'cli.cycle_mode' and request.get('expected_mode') != self.status()['selected_mode']:
                raise ValueError('运行模式已变化，请等待最新状态后重新切换')
            if op == 'cli.stop' and request.get('run') != (self.manager.radio_run or {}).get('scope'):
                raise ValueError('运行已切换；旧停止请求未执行，请重新读取状态')
            result = self.manager.operate(op.split('.')[1])
            if not result:
                raise ValueError('CLI操作未完成：' + self.manager.phase)
            return {'submitted': op == 'cli.start', **self.status()}
        if self.store is None:
            raise ValueError('配置服务不可用：' + str(self.config_error))
        if op == 'config.list':
            return {'modules': self.store.list()}
        if op == 'config.read':
            return self.store.read(request['module'])
        if op == 'config.set':
            result = self.store.save(request['updates'])
            self.manager.emit('[配置] 已保存：' + ', '.join(result['saved']) + '；重启生效。', 'ok')
            self.manager.publish()
            return result
        raise ValueError('Unknown CLI API operation')

    def pump(self):
        # Called only by the same worker which executes local Manager.command.
        def order(path):
            priority = False
            try:
                if path.stat().st_size <= 262144:
                    request = json.loads(path.read_text(encoding='utf-8'))
                    priority = request.get('op') in ('cli.check', 'cli.start', 'cli.stop',
                                                    'cli.status', 'cli.result', 'config.set', 'cli.cycle_mode')
            except (OSError, ValueError, TypeError, AttributeError):
                pass  # Normal validation below produces the persisted error.
            return (not priority, path.stat().st_mtime_ns, path.name)

        pending = sorted(self.inbox.glob('*.json'), key=order)
        if not pending:
            return
        path = pending[0]
        ident = path.stem
        if not valid_id(ident):
            path.rename(path.with_suffix('.invalid'))
            return
        result_path = self.results / path.name
        if result_path.exists():
            path.unlink(missing_ok=True)
            return  # Persisted results, including in-progress records, prohibit re-execution.
        request_hash = None
        try:
            if path.stat().st_size > 262144:
                raise ValueError('CLI request exceeds 256 KiB')
            request = json.loads(path.read_text(encoding='utf-8'))
            request_hash = hashlib.sha256(json.dumps(request, sort_keys=True, ensure_ascii=False,
                                                     separators=(',', ':')).encode()).hexdigest()
            if request['id'] != ident:
                raise ValueError('Request identity does not match mailbox name')
            if int(request['expires_ns']) < time.time_ns():
                raise ValueError('指令已过期，未执行')
            self.active = {'id': ident, 'op': request['op'], 'stage': 'executing'}
            atomic_json(result_path, {'id': ident, 'boot': self.boot, 'stage': 'executing',
                                      'request_hash': request_hash})
            self.manager.publish()
            result = self.execute(request)
            encoded = json.dumps(result, ensure_ascii=False, allow_nan=False).encode('utf-8')
            if len(encoded) > 250000:
                raise ValueError('CLI result is too large; narrow the requested module')
            response = {'id': ident, 'boot': self.boot, 'ok': True, 'stage': 'complete', 'result': result}
        except Exception as exc:
            response = {'id': ident, 'boot': self.boot, 'ok': False, 'stage': 'complete', 'error': str(exc)}
            self.manager.emit('[接口] 操作失败：' + str(exc), 'error')
        response['source_stamp_ns'] = str(time.time_ns())
        response['request_hash'] = request_hash
        atomic_json(result_path, response)
        self.last = {key: response[key] for key in ('id', 'ok', 'stage', 'source_stamp_ns')}
        self.active = None
        path.unlink(missing_ok=True)


def main():
    import argparse
    parser = argparse.ArgumentParser(description='调用CLI统一接口；管理进程必须已常驻')
    parser.add_argument('operation', choices=['cli.status', 'cli.result', 'cli.check', 'cli.start', 'cli.stop',
                                            'config.list', 'config.read', 'config.set', 'cli.cycle_mode'])
    parser.add_argument('--module')
    parser.add_argument('--request-id', help='cli.result查询的原始请求ID')
    parser.add_argument('--updates', help='JSON模块修改列表，含revision和changes')
    args = parser.parse_args()
    directory = Path(__file__).resolve().parents[1] / '.runtime/fsd_manager/control'
    state = json.loads((directory / 'heartbeat.json').read_text(encoding='utf-8'))
    if not state.get('online') or time.time_ns() - int(state['updated_ns']) > 5_000_000_000:
        raise SystemExit('CLI管理进程未在线')
    ident = uuid.uuid4().hex
    request = {'id': ident, 'op': args.operation, 'boot': state['boot'], 'run': state.get('run'),
               'expires_ns': str(time.time_ns() + 180_000_000_000),
               'source_stamp_ns': str(time.time_ns())}
    if args.operation == 'cli.cycle_mode':
        request['expected_mode'] = state.get('selected_mode')
    if args.request_id:
        request['request_id'] = args.request_id
    if args.module:
        request['module'] = args.module
    if args.updates:
        request['updates'] = json.loads(args.updates)
    atomic_json(directory / 'inbox' / (ident + '.json'), request)
    deadline = time.monotonic() + 185
    while time.monotonic() < deadline:
        path = directory / 'results' / (ident + '.json')
        if path.exists():
            response = json.loads(path.read_text(encoding='utf-8'))
            if response.get('stage') == 'complete':
                print(json.dumps(response, ensure_ascii=False, indent=2))
                return 0 if response['ok'] else 1
        time.sleep(.2)
    raise SystemExit('结果未知；请查询CLI状态，勿重复提交新的启动指令。请求ID=' + ident)


if __name__ == '__main__':
    raise SystemExit(main())
