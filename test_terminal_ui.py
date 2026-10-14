"""Drive the keyboard-only Textual interface without starting vehicle hardware."""
import asyncio
import json
import sys
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / '.runtime/fsd_manager/ui_deps'))
sys.path.insert(0, str(Path(__file__).parent))
from manager import Manager
from terminal_ui import FsdApp
from textual.widgets import Button, DataTable, Input, OptionList, RichLog, Select


def test_menu_keyboard_check_errors_views_and_exit(tmp_path):
    import manager
    import terminal_ui

    def failure(_):
        raise PermissionError('serial ACL test failure')

    async def scenario():
        instance = Manager([], color=False)
        app = FsdApp(instance, telemetry=False)
        try:
            async with app.run_test(size=(110, 36)) as pilot:
                await pilot.pause(.4)
                assert not list(app.query(Button))
                assert not list(app.query(Input))
                assert not list(app.query('#command'))
                assert app.no_color is False
                await pilot.press('c')
                for _ in range(30):
                    await pilot.pause(.1)
                    if app.state_data.get('checks'):
                        break
                assert app.state_data['checks']['华测串口']['ok'] is False
                assert app.query_one('#check-table', DataTable).row_count == len(manager.CHECKS) + len(instance.runtime_checks.rows)
                table = app.query_one('#check-table', DataTable)
                table.focus()
                await pilot.press('enter')
                assert 'serial ACL test failure' in app.content()
                assert 'Traceback' in app.content()
                table.move_cursor(row=len(manager.CHECKS))
                await pilot.press('enter')
                assert app.selected_check == 'rt:sudo'
                assert '待启动验证' in app.content()
                await pilot.press('3')
                assert app.view == 'checks'
                await pilot.press('tab')
                assert app.focused is app.query_one('#detail', RichLog)
                await pilot.press('shift+tab', 'shift+tab')
                assert app.focused is app.query_one('#views', OptionList)
                await pilot.press('down', 'down', 'enter')
                assert app.view == 'sensors'
                assert not table.display
                app.query_one('#views', OptionList).focus()
                await pilot.press('home')
                await pilot.press('down', 'enter')
                assert app.view == 'vehicle'
                app.change_view('logs')
                app.action_pause_log()
                assert app.paused
                app.action_pause_log()
                app.change_view('modules')
                assert app.query_one('#component').display
                await pilot.resize_terminal(80, 24)
                await pilot.pause(.2)
                assert app.query_one('#keys').region.bottom <= 24
                await pilot.resize_terminal(65, 24)
                await pilot.pause(.2)
                assert app.query_one('#sidebar').display
                for index, view in enumerate(['checks', 'vehicle', 'sensors', 'logs', 'modules', 'config']):
                    app.query_one('#views', OptionList).focus()
                    await pilot.press('home', *(['down'] * index), 'enter')
                    assert app.view == view
                app.query_one('#detail', RichLog).focus()
                await pilot.press('tab')
                assert app.focused is not None
                app.query_one('#views', OptionList).focus()
                await pilot.press('q')
                for _ in range(30):
                    await pilot.pause(.1)
                    if app.done.is_set():
                        break
                assert app.done.is_set()
            assert not app.owner.is_alive()
        finally:
            instance.log.close()

    with patch.object(manager, 'ROOT', tmp_path), patch.object(manager, 'RUNTIME', tmp_path), \
            patch.object(manager, 'CHECKS', {'华测串口': failure}), \
            patch.object(terminal_ui, 'CHECKS', {'华测串口': failure}):
        asyncio.run(scenario())


def test_module_configuration_selector_keyboard_refresh_and_errors(tmp_path):
    import manager

    async def scenario():
        instance = Manager([], color=False)
        app = FsdApp(instance, telemetry=False)
        manifest = {'files': {'controller': '/custom/controller.yaml', 'can': '/custom/can.yaml'},
                    'parameters': {'controller': {'speed_limit': 2.0}, 'can': {'can': {'device': 'can0'}}},
                    'deployment': {'can_device': 'can1'}}
        try:
            async with app.run_test(size=(110, 36)) as pilot:
                await pilot.pause(.3)
                await pilot.press('end', 'enter')
                assert app.view == 'config'
                assert '尚无配置清单' in app.content()
                selector = app.query_one('#module-config', Select)
                assert selector.display and not app.query_one('#component').display
                manager.save(tmp_path / 'manifest.json', manifest)
                await pilot.pause(.4)
                await pilot.press('tab')
                assert app.focused is selector
                await pilot.press('enter', 'home', 'down', 'down', 'enter')
                assert selector.value == 'can'
                content = app.content()
                assert selector.content_region.height >= selector.query_one('SelectCurrent').region.height
                assert '/custom/can.yaml' in content and 'can1' in content
                assert 'speed_limit' not in content
                manifest['parameters']['can']['can']['device'] = 'can2'
                manager.save(tmp_path / 'manifest.json', manifest)
                await pilot.pause(.4)
                assert selector.value == 'can'
                assert 'can2' in app.content()
                app.query_one('#views', OptionList).focus()
                await pilot.press('home', 'down', 'down', 'down', 'down', 'enter')
                assert app.view == 'modules'
                assert not selector.display and app.query_one('#component').display
                await pilot.press('end', 'enter')
                assert app.view == 'config' and selector.value == 'can'
                selector.focus()
                await pilot.press('enter', 'home', 'enter')
                assert selector.value == '__all__' and 'speed_limit' in app.content()
                (tmp_path / 'manifest.json').write_text('{broken')
                await pilot.pause(.4)
                assert '配置清单读取失败' in app.content()
                manager.save(tmp_path / 'manifest.json', manifest)
                await pilot.pause(.4)
                assert 'speed_limit' in app.content()
                selector.value = 'can'
                await pilot.pause(.1)
                del manifest['files']['can']
                del manifest['parameters']['can']
                manager.save(tmp_path / 'manifest.json', manifest)
                await pilot.pause(.4)
                assert selector.value == '__all__'
                app.action_quit()
                await pilot.pause(.4)
            assert not app.owner.is_alive()
        finally:
            instance.log.close()

    with patch.object(manager, 'ROOT', tmp_path), patch.object(manager, 'RUNTIME', tmp_path):
        asyncio.run(scenario())
