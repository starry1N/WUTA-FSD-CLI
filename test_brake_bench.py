"""CLI-only bench selection; no real launch/permissions or hardware operations."""
import asyncio
from pathlib import Path
import sys
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent))
import manager
from manager import Manager, options_from
import checks
from runtime_checks import RuntimeChecks


def test_mode_is_session_only_and_locked_until_stopped(tmp_path):
    with patch.object(manager, 'ROOT', tmp_path), patch.object(manager, 'RUNTIME', tmp_path):
        instance = Manager(['--no-rviz'], color=False)
        try:
            assert instance.cycle_run_profile()
            assert '--brake-bench' in instance.args
            assert instance.options['_rviz'] is False
            assert instance.control.store is None or instance.control.store.options is instance.options
            instance.child = SimpleNamespace(poll=lambda: None)
            assert not instance.cycle_run_profile()
            instance.child = None
            instance.run_log = SimpleNamespace(data={'mode': 'brake_bench', 'run_id': 'test'})
            assert not instance.cycle_run_profile()
            instance.run_log = None
            assert instance.cycle_run_profile()
            assert instance.options['manual-record']
            assert instance.cycle_run_profile()
            assert instance.args == ['--no-rviz']
            assert 'brake-bench' not in instance.options
        finally:
            instance.log.close()
        fresh = Manager([], color=False)
        assert 'brake-bench' not in fresh.options
        fresh.log.close()


def test_bench_checks_skip_sensor_dependencies_and_preserve_can():
    options = options_from(['--brake-bench'])
    for function in (checks.serial, checks.lidar, checks.calibration, checks.visualization):
        assert function(options).startswith('跳过')
    progress = RuntimeChecks(options)
    assert progress.rows['process:controller']['status'] != '跳过'
    assert progress.rows['process:can_interface']['status'] != '跳过'
    assert progress.rows['process:mission_manager']['status'] != '跳过'
    assert progress.rows['process:chcnav']['status'] == '跳过'
    assert progress.rows['topic:定位输出']['status'] == '跳过'
    assert set(checks.configuration(options)['files']) == {'controller', 'can', 'mission'}


def test_keyboard_mode_toggle_and_restore(tmp_path):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / '.runtime/fsd_manager/ui_deps'))
    from terminal_ui import FsdApp
    async def scenario():
        instance = Manager([], color=False)
        app = FsdApp(instance, telemetry=False)
        try:
            async with app.run_test(size=(100, 30)) as pilot:
                await pilot.pause(.4)
                await pilot.press('m')
                await pilot.pause(.4)
                assert app.state_data['selected_mode'] == 'brake_bench'
                await pilot.press('m')
                await pilot.pause(.4)
                assert app.state_data['selected_mode'] == 'manual_record'
                await pilot.press('m')
                await pilot.pause(.4)
                assert app.state_data['selected_mode'] == 'normal'
                await pilot.press('q')
                await pilot.pause(.4)
        finally:
            instance.log.close()
    with patch.object(manager, 'ROOT', tmp_path), patch.object(manager, 'RUNTIME', tmp_path):
        asyncio.run(scenario())


def test_editor_validates_bench_before_writing(tmp_path):
    import shutil
    import pytest
    from config_store import ConfigStore
    import check_fsd_module_configs as audit
    files = {}
    for key in ('controller', 'can', 'mission'):
        destination = tmp_path / (key + '.yaml')
        shutil.copyfile(audit.module_files()[key], destination)
        files[key] = destination
    with patch.object(audit, 'module_files', return_value=files):
        store = ConfigStore(tmp_path, {'brake-bench': True})
        current = store.read('controller')
        before = files['controller'].read_bytes()
        key = '/controller_node/ros__parameters/acceleration/bench_brake/opening'
        with pytest.raises(ValueError):
            store.save([{'module': 'controller', 'revision': current['revision'], 'changes': {key: 1.1}}])
        assert files['controller'].read_bytes() == before
        key = '/controller_node/ros__parameters/acceleration/bench_brake/hold_sec'
        result = store.save([{'module': 'controller', 'revision': current['revision'], 'changes': {key: 9.0}}])
        assert result['saved'] == ['controller']
        assert audit.parameters(files['controller'])['acceleration']['bench_brake']['hold_sec'] == 9.0


def test_root_stops_controller_before_can_without_touching_processes(tmp_path):
    import subprocess
    root = Path(__file__).resolve().parents[1]
    source = (root / 'start_full_fsd.sh').read_text()
    cleanup = 'cleanup() {' + source.split('cleanup() {', 1)[1].split('\n}\n', 1)[0] + '\n}\n'
    harness = '''
BRAKE_BENCH=1
CHILD_NAMES=(controller can_interface mission_manager)
CHILD_PIDS=(101 102 103)
OBSERVER_PIDS=()
kill() { echo "kill:$*" >> events; [[ "$1" != -0 ]]; }
sleep() { echo "sleep:$*" >> events; }
wait() { return 0; }
supervisor_alive() { return 1; }
'''
    result = subprocess.run(['bash', '-c', harness + cleanup + 'cleanup'], cwd=tmp_path,
                            capture_output=True, text=True, timeout=3)
    assert result.returncode == 0, result.stderr
    lines = (tmp_path / 'events').read_text().splitlines()
    assert lines[0] == 'kill:-INT -- -101'
    assert lines[1] == 'sleep:0.7'
    assert lines.index('kill:-INT -- -102') > 1
