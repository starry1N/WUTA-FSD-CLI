"""Local CLI editor using the same queued API as the wireless client."""
import json
import time

from textual.app import ComposeResult
from textual.containers import Vertical, Horizontal
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Select, Static


class ConfigEditor(ModalScreen):
    BINDINGS = [('escape', 'dismiss', '关闭')]
    DEFAULT_CSS = """
    ConfigEditor { align: center middle; }
    #config-dialog { width: 95%; height: 90%; border: round #89b4fa; padding: 1 2; background: #1e1e2e; }
    #edit-source { height: 3; }
    #edit-status { height: 1fr; }
    #edit-buttons { height: 3; }
    #edit-buttons Button { margin-right: 1; }
    """

    def __init__(self, manager):
        super().__init__()
        self.control = manager.control
        self.pending = None
        self.files, self.drafts = {}, {}
        self.module = None
        self.selected_path = None
        self.last_save = ''

    def compose(self) -> ComposeResult:
        with Vertical(id='config-dialog'):
            yield Static('模块配置编辑 · 草稿 → Linux校验保存 → 重启相关进程生效')
            yield Select([], prompt='选择模块', id='edit-module')
            yield Static('等待读取实际文件', id='edit-source', markup=False)
            yield Select([], prompt='选择参数路径', id='edit-path')
            yield Input(placeholder='JSON值，例如 1.2、true、"文本"、[1,2,3]', id='edit-value')
            with Horizontal(id='edit-buttons'):
                yield Button('暂存此参数', id='edit-stage')
                yield Button('保存全部草稿', variant='primary', id='edit-save')
                yield Button('关闭', id='edit-close')
            yield Static('读取中；关闭会丢弃尚未提交的草稿。', id='edit-status', markup=False)

    def on_mount(self):
        self.request('config.list')
        self.set_interval(.2, self.poll)

    def note(self, text):
        self.query_one('#edit-status', Static).update(str(text))

    def request(self, operation, **args):
        if self.pending:
            self.note('请等待当前CLI请求完成')
            return False
        try:
            ident = self.control.submit(operation, **args)
        except (OSError, ValueError) as exc:
            self.note(exc)
            return False
        self.pending = (ident, operation, time.monotonic())
        self.query_one('#edit-module', Select).disabled = True
        return True

    def poll(self):
        if not self.pending:
            return
        ident, operation, began = self.pending
        path = self.control.results / (ident + '.json')
        try:
            if not path.exists():
                if time.monotonic() - began > 185:
                    self.note('结果未知，请查看CLI状态。ID=' + ident)
                    self.pending = None
                    self.query_one('#edit-module', Select).disabled = False
                return
            response = json.loads(path.read_text(encoding='utf-8'))
            if response.get('stage') != 'complete':
                return
            self.pending = None
            self.query_one('#edit-module', Select).disabled = False
            if not response.get('ok'):
                self.note('CLI失败：' + str(response.get('error')))
                return
            result = response['result']
            if operation == 'config.list':
                options = [(row['module'], row['module']) for row in result['modules'] if row['available']]
                self.query_one('#edit-module', Select).set_options(options)
                self.note('选择模块后读取Linux当前文件；JSON值必须保持原类型。')
            elif operation == 'config.read':
                module = result['module']
                self.files[module] = result
                self.show_file(module)
            elif operation == 'config.set':
                self.files.clear()
                self.drafts.clear()
                self.last_save = result['message']
                self.note(self.last_save)
                if self.module:
                    self.request('config.read', module=self.module)
        except (OSError, ValueError, KeyError, TypeError) as exc:
            self.note(exc)
            self.pending = None
            self.query_one('#edit-module', Select).disabled = False

    def show_file(self, module):
        result = self.files[module]
        self.query_one('#edit-source', Static).update(result['source'] + '\nrevision: ' + result['revision'])
        self.query_one('#edit-path', Select).set_options([(row['path'], row['path']) for row in result['parameters']])
        self.selected_path = None
        self.query_one('#edit-value', Input).value = ''
        self.note(self.last_save + '\n已读取文件；不是节点在线参数。待确认重启加载：' + str(result['restart_required']))

    def on_select_changed(self, event: Select.Changed):
        event.stop()
        if event.value is Select.BLANK:
            return
        if event.select.id == 'edit-module':
            if self.pending:
                self.note('请等待读取/保存完成，再切换模块')
                return
            self.module = str(event.value)
            if self.module in self.files:
                self.show_file(self.module)
            else:
                self.request('config.read', module=self.module)
        elif event.select.id == 'edit-path' and self.module in self.files:
            self.selected_path = str(event.value)
            values = {row['path']: row['value'] for row in self.files[self.module]['parameters']}
            value = self.drafts.get(self.module, {}).get(self.selected_path, values[self.selected_path])
            self.query_one('#edit-value', Input).value = json.dumps(value, ensure_ascii=False)

    def on_button_pressed(self, event: Button.Pressed):
        if event.button.id == 'edit-close':
            self.dismiss()
            return
        if self.pending:
            self.note('请等待当前请求完成')
            return
        try:
            if event.button.id == 'edit-stage':
                if self.module not in self.files or not self.selected_path:
                    raise ValueError('请先选择模块和参数')
                value = json.loads(self.query_one('#edit-value', Input).value,
                                   parse_constant=lambda v: (_ for _ in ()).throw(ValueError(v)))
                self.drafts.setdefault(self.module, {})[self.selected_path] = value
                self.note('已暂存，尚未保存。草稿参数数：' + str(sum(len(v) for v in self.drafts.values())))
            elif event.button.id == 'edit-save':
                updates = [{'module': module, 'revision': self.files[module]['revision'], 'changes': edits}
                           for module, edits in self.drafts.items() if edits]
                if not updates:
                    raise ValueError('没有待保存的草稿')
                self.request('config.set', updates=updates)
                self.note('等待CLI校验与保存；不会自动重启进程。')
        except (ValueError, KeyError, TypeError) as exc:
            self.note(exc)
