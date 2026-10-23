"""Human driving profile: no hardware or real process mutation."""
import asyncio
from pathlib import Path
import sys
from types import SimpleNamespace
from unittest.mock import patch
import pytest
sys.path.insert(0, str(Path(__file__).parent))
import manager
from manager import Manager, options_from
from runtime_checks import RuntimeChecks
from log_context import RunLog


def test_select_lock_and_restore(tmp_path):
    with patch.object(manager, 'ROOT', tmp_path), patch.object(manager, 'RUNTIME', tmp_path):
        instance = Manager(['--no-rviz', '--brake-bench'], color=False)
        try:
            assert instance.cycle_run_profile()
            assert instance.options['manual-record']
            instance.child = SimpleNamespace(poll=lambda: None)
            assert not instance.cycle_run_profile()
            instance.child = None
            instance.run_log = SimpleNamespace(data={'mode': 'manual_record', 'run_id': 'test'})
            assert not instance.cycle_run_profile()
            instance.run_log = None
            assert instance.cycle_run_profile()
            assert instance.args == ['--no-rviz']
        finally:
            instance.log.close()


def test_full_logs_and_no_controller(tmp_path):
    run = RunLog.create(tmp_path, mode='manual_record')
    assert run.path.parent.name == 'manual_record'
    assert all((run.path / name).is_dir() for name in ('trajectory', 'fsd_modules', 'chcnav_log', 'zlgCAN_log', 'configs', 'ros'))
    run.finish(0, 'test')
    assert run.path.parent.name == 'manual_record'
    checks = RuntimeChecks(options_from(['--manual-record']))
    assert checks.rows['process:controller']['status'] == '跳过'
    for name in ('zlg_can', 'can_interface', 'mission_manager', 'path_generator', 'ekf', 'localization_manager'):
        assert checks.rows['process:' + name]['status'] != '跳过'
    with pytest.raises(ValueError):
        options_from(['--manual-record', '--brake-bench'])


def test_keyboard_record_mode(tmp_path):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / '.runtime/fsd_manager/ui_deps'))
    from terminal_ui import FsdApp
    async def scenario():
        instance = Manager([], color=False)
        app = FsdApp(instance, telemetry=False)
        try:
            async with app.run_test(size=(100, 30)) as pilot:
                await pilot.pause(.3)
                await pilot.press('m'); await pilot.pause(.3)
                assert app.state_data['selected_mode'] == 'brake_bench'
                await pilot.press('m'); await pilot.pause(.3)
                assert app.state_data['selected_mode'] == 'manual_record'
                await pilot.press('r'); await pilot.pause(.3)
                assert app.state_data['selected_mode'] == 'manual_record'
                await pilot.press('m'); await pilot.pause(.3)
                assert app.state_data['selected_mode'] == 'normal'
                await pilot.press('q')
        finally:
            instance.log.close()
    with patch.object(manager, 'ROOT', tmp_path), patch.object(manager, 'RUNTIME', tmp_path):
        asyncio.run(scenario())


def test_real_shell_launch_plan_keeps_full_chain_without_controller(tmp_path):
    import subprocess
    source = (Path(__file__).resolve().parents[1] / 'start_full_fsd.sh').read_text()
    block = source.split('\nreconnect_can_bridge\n', 1)[1].split('\nif [[ "$RVIZ" == 1 ]]; then', 1)[0]
    harness = r'''
MANUAL_RECORD=1
BRAKE_BENCH=0
SENSOR_ONLY=0
REUSE_INS=1
ROOT=/nonexistent
FSD_WS=/fake/fsd
RUN_DIR=/fake/logs
FSD_MODULES_DIR=/fake/logs/modules
BASE_TF=(0 0 0 0 0 0 1)
MODEL=/fake/model
CALIBRATION=/fake/calibration
CONTROLLER_CONFIG=/fake/controller
CAN_CONFIG=/fake/can
CAN_IFACE=can0
CAN_IFACE_EXPLICIT=1
LIDAR_TOPIC=/lidar
IMAGE_TOPIC=/image
FUSION_TOPIC=/fusion
INS_TOPIC=/ins
start_group() { printf '%s\n' "$*"; }
wait_topic() { :; }
report_ok() { :; }
'''
    result = subprocess.run(['bash', '-eu', '-c', harness + block], capture_output=True, text=True, timeout=5)
    assert result.returncode == 0, result.stderr
    lines = result.stdout.splitlines()
    assert not any(line.startswith('controller ') for line in lines)
    assert any(line.startswith('can_interface ') and 'receive_only:=true' in line for line in lines)
    assert any(line.startswith('mission_manager ') and 'manual_record_mode:=true' in line for line in lines)
    for name in ('ekf', 'localization_manager', 'cone_map_builder', 'boundary_detector', 'path_generator', 'perception'):
        assert any(line.startswith(name + ' ') for line in lines), name
