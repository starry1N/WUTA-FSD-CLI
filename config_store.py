"""Shared CLI configuration operations. No ROS or process control in this module."""
import base64
import hashlib
import json
import math
import os
from pathlib import Path
import sys
import time
import uuid

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
import check_fsd_module_configs as audit


def atomic_bytes(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + '.' + uuid.uuid4().hex + '.tmp')
    try:
        with temporary.open('xb') as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        if path.exists():
            os.chmod(temporary, path.stat().st_mode & 0o777)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def atomic_json(path, value):
    atomic_bytes(path, json.dumps(value, ensure_ascii=False, allow_nan=False).encode('utf-8'))


def revision(data):
    return hashlib.sha256(data).hexdigest()


def pointer(parts):
    return '/' + '/'.join(str(p).replace('~', '~0').replace('/', '~1') for p in parts)


def leaves(value, parts=()):
    if isinstance(value, dict):
        for key, child in value.items():
            if not isinstance(key, str):
                raise ValueError('YAML mapping keys must be strings')
            yield from leaves(child, (*parts, key))
    elif isinstance(value, list) and any(isinstance(v, (dict, list)) for v in value):
        for index, child in enumerate(value):
            yield from leaves(child, (*parts, index))
    elif value is not None:
        if isinstance(value, list):
            for item in value:
                if type(item) not in (str, bool, int, float):
                    raise ValueError('Only scalar arrays are exposed as editable parameters')
        elif type(value) not in (str, bool, int, float):
            raise ValueError('Unsupported YAML scalar type: ' + type(value).__name__)
        for item in (value if isinstance(value, list) else [value]):
            if isinstance(item, float) and not math.isfinite(item):
                raise ValueError('Non-finite YAML values are not exposed')
            if type(item) is int and not -(2**63) <= item < 2**63:
                raise ValueError('Parameter integers must fit signed 64 bits')
        yield pointer(parts), value


def typed_value(old, new):
    if isinstance(old, list):
        if not isinstance(new, list) or len(old) != len(new):
            raise ValueError('Array edits must preserve length to retain YAML comments')
        return [typed_value(a, b) for a, b in zip(old, new)]
    if isinstance(old, float) and isinstance(new, (float, int)) and not isinstance(new, bool):
        new = float(new)
    elif type(new) is not type(old):
        raise ValueError(f'Expected {type(old).__name__}, received {type(new).__name__}')
    if isinstance(new, float) and not math.isfinite(new):
        raise ValueError('Non-finite values are not allowed')
    if not isinstance(new, (str, bool, int, float)):
        raise ValueError('Only scalar values and scalar arrays may be edited')
    return new


def patch_document(text, changes):
    document = yaml.safe_load(text)
    existing = dict(leaves(document))
    unknown = set(changes) - set(existing)
    if unknown:
        raise ValueError('Unknown parameter paths: ' + ', '.join(sorted(unknown)))
    typed = {path: typed_value(existing[path], value) for path, value in changes.items()}
    nodes, seen = {}, set()

    def walk(node, parts=()):
        if id(node) in seen:
            raise ValueError('YAML aliases require offline editing; no ambiguous patch is written')
        seen.add(id(node))
        nodes[pointer(parts)] = node
        if isinstance(node, yaml.MappingNode):
            keys = set()
            for key, child in node.value:
                if key.value in keys:
                    raise ValueError('Duplicate YAML mapping keys require offline editing')
                keys.add(key.value)
                if key.value == '<<':
                    raise ValueError('YAML merge keys require offline editing')
                walk(child, (*parts, key.value))
        elif isinstance(node, yaml.SequenceNode):
            for index, child in enumerate(node.value):
                walk(child, (*parts, index))

    walk(yaml.compose(text))
    edits = []

    def replace(node, value):
        if isinstance(value, list):
            for child, item in zip(node.value, value):
                replace(child, item)
        else:
            encoded = json.dumps(value, ensure_ascii=False, allow_nan=False)
            original = text[node.start_mark.index:node.end_mark.index]
            if original.endswith('\n'):
                encoded += '\n'
            edits.append((node.start_mark.index, node.end_mark.index, encoded))

    for path, value in typed.items():
        replace(nodes[path], value)
    for start, end, encoded in sorted(edits, reverse=True):
        text = text[:start] + encoded + text[end:]
    result = yaml.safe_load(text)
    actual = dict(leaves(result))
    for path, value in typed.items():
        if actual[path] != value:
            raise ValueError('YAML patch did not preserve the requested value')
    return text, result


class ConfigStore:
    def __init__(self, root, options):
        self.root, self.options = Path(root), options
        self.directory = self.root / '.runtime/fsd_manager/control'
        self.transactions = self.directory / 'transactions'
        self.transactions.mkdir(parents=True, exist_ok=True)
        self.state_path = self.directory / 'config_state.json'
        self.pending = json.loads(self.state_path.read_text(encoding='utf-8')) if self.state_path.exists() else {}
        self.recover()

    def catalog(self):
        return audit.configuration_files(
            self.options.get('controller-config'), self.options.get('can-config'),
            self.options.get('calibration', os.environ.get('CALIBRATION')),
            self.options.get('base-to-zed', os.environ.get('BASE_TO_ZED')))

    def path(self, module):
        if module not in self.catalog():
            raise ValueError('Unknown configuration module')
        return self.catalog()[module].expanduser().resolve(strict=True)

    def manifest(self, documents=None):
        if 'brake-bench' in self.options:
            return audit.brake_bench_manifest(self.options.get('controller-config'), self.options.get('can-config'),
                                              os.environ.get('CAN_IFACE', ''), documents=documents)
        return audit.manifest(self.options.get('controller-config'), self.options.get('can-config'),
                              self.options.get('model', os.environ.get('MODEL', '')),
                              os.environ.get('CAN_IFACE', ''), documents=documents)

    def list(self):
        return [{'module': key, 'source': str(path.resolve()), 'available': path.is_file()}
                for key, path in self.catalog().items()]

    def read(self, module):
        path = self.path(module)
        data = path.read_bytes()
        document = yaml.safe_load(data.decode('utf-8'))
        return {'module': module, 'source': str(path), 'revision': revision(data),
                'restart_required': module in self.pending,
                'parameters': [{'path': key, 'value': value} for key, value in leaves(document)]}

    def recover(self):
        for path in self.transactions.glob('*.json'):
            transaction = json.loads(path.read_text(encoding='utf-8'))
            if transaction['stage'] != 'committing':
                continue
            for row in transaction['files']:
                target = self.path(row['module'])
                if str(target) != row['source']:
                    raise ValueError('Unfinished configuration transaction uses another source path')
                data = target.read_bytes()
                if revision(data) == row['after']:
                    atomic_bytes(target, base64.b64decode(row['before'], validate=True))
                elif revision(data) != row['revision']:
                    raise ValueError('Configuration changed during crash recovery; inspect ' + str(path))
            self.pending = transaction.get('pending_before', self.pending)
            atomic_json(self.state_path, self.pending)
            atomic_json(self.root / '.runtime/fsd_manager/manifest.json', self.manifest())
            transaction['stage'] = 'rolled_back'
            atomic_json(path, transaction)

    def save(self, updates):
        if not isinstance(updates, list) or not 1 <= len(updates) <= len(self.catalog()):
            raise ValueError('updates must contain one or more module edits')
        self.recover()
        prepared, documents, modules = [], {}, set()
        for update in updates:
            module = update['module']
            if module in modules:
                raise ValueError('A module may appear only once per transaction')
            modules.add(module)
            path = self.path(module)
            if any(path == row[0] for row in prepared):
                raise ValueError('Multiple module keys resolve to the same configuration file')
            original = path.read_bytes()
            if revision(original) != update['revision']:
                raise ValueError(module + ': file changed; reload before saving')
            changes = update['changes']
            if not isinstance(changes, dict) or not changes:
                raise ValueError('Each module must contain parameter changes')
            patched, document = patch_document(original.decode('utf-8'), changes)
            documents[module] = document
            prepared.append((path, original, patched.encode('utf-8'), module))
        audited = self.manifest(documents)
        transaction = {'stage': 'committing', 'pending_before': dict(self.pending), 'files': [
            {'module': module, 'source': str(path), 'revision': revision(before),
             'after': revision(after), 'before': base64.b64encode(before).decode('ascii')}
            for path, before, after, module in prepared]}
        journal = self.transactions / (uuid.uuid4().hex + '.json')
        atomic_json(journal, transaction)
        try:
            for path, before, after, module in prepared:
                if revision(path.read_bytes()) != revision(before):
                    raise ValueError(module + ': file changed during save')
                atomic_bytes(path, after)
            atomic_json(self.root / '.runtime/fsd_manager/manifest.json', audited)
            self.pending.update({module: time.time_ns() for module in modules})
            atomic_json(self.state_path, self.pending)
            transaction['stage'] = 'committed'
            atomic_json(journal, transaction)
        except Exception:
            self.recover()
            raise
        return {'saved': sorted(modules), 'restart_required': True,
                'message': 'Linux已保存；需重启相应进程生效，未在线改写算法。'}

