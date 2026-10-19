"""Lifecycle regression without launching hardware or changing the ROS domain."""
import json
from pathlib import Path
import sys
import subprocess
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from log_context import RunLog, write_json
from mission_diagnostics import describe
from manager import Manager


def test_mission_at_start_creates_project_directory(tmp_path):
    run = RunLog.create(tmp_path, mission='acceleration', mission_source='vcu_mode_cache')
    original = run.path
    (original / 'trajectory/driven.csv').write_text('payload\n')
    destination = run.finish(0, 'test_exit')
    assert destination == original
    assert destination.parent.name == 'acceleration'
    assert (destination / 'trajectory/driven.csv').read_text() == 'payload\n'
    data = json.loads((destination / 'run.json').read_text())
    assert data['mission'] == 'acceleration'
    assert data['path'] == str(destination)


def test_pending_run_moves_after_fallback_mission(tmp_path):
    run = RunLog.create(tmp_path, mission_source='fallback_pending')
    original = run.path
    assert original.parent.name == 'pending'
    # Simulate the read-only monitor updating run.json while the owner keeps
    # its in-memory copy from startup.
    data = json.loads((original / 'run.json').read_text())
    data['mission'] = 'trackdrive'
    data['mission_source'] = 'fallback_observed'
    write_json(original / 'run.json', data)
    destination = run.finish(0, 'test_exit')
    assert destination.parent.name == 'trackdrive'
    assert not original.exists()


def test_archive_never_overwrites_and_explicit_output_stays_put(tmp_path):
    run = RunLog.create(tmp_path, mission_source='fallback_pending')
    run.data['mission'] = 'acceleration'
    run.save()
    destination = tmp_path / 'wuta_logs/acceleration' / run.path.name
    destination.mkdir(parents=True)
    with pytest.raises(FileExistsError):
        run.finish(0, 'test')
    assert run.path.exists()
    explicit = RunLog.create(tmp_path, mode='simulation', mission='skidpad', path=tmp_path/'custom')
    assert explicit.finish(0, 'test') == tmp_path/'custom'


def test_archive_keeps_driver_latest_link_usable(tmp_path):
    run = RunLog.create(tmp_path, mission_source='fallback_pending')
    run.data['mission'] = 'acceleration'
    run.save()
    driver = run.path/'chcnav_log'
    session = driver/'123'
    session.mkdir(parents=True)
    (session/'events.log').write_text('driver-event')
    (driver/'latest').symlink_to(session)
    destination = run.finish(0, 'test')
    assert (destination/'chcnav_log/latest/events.log').read_text() == 'driver-event'


def test_recovery_marks_interrupted_run_after_cleanup(tmp_path):
    import manager
    run = RunLog.create(tmp_path, mission_source='fallback_pending')
    run.data['mission'] = 'skidpad'
    run.save()
    write_json(tmp_path/'state.json', {'log_dir': str(run.path)})
    with patch.object(manager, 'ROOT', tmp_path), patch.object(manager, 'RUNTIME', tmp_path):
        instance = Manager([], color=False)
        try:
            instance.recover()
            destination = Path(instance.log_dir)
            assert destination.parent.name == 'skidpad'
            assert json.loads((destination/'run.json').read_text())['reason'] == 'recovered_after_manager_exit'
        finally:
            instance.log.close()


def test_failed_precheck_retry_and_tail_do_not_duplicate_log(tmp_path, capsys):
    import manager
    with patch.object(manager, 'ROOT', tmp_path), patch.object(manager, 'RUNTIME', tmp_path):
        instance = Manager([], color=False)
        try:
            with patch.object(instance, 'permissions', return_value=False):
                instance.start()
                instance.start()
            runs = list((tmp_path/'wuta_logs/pending').iterdir())
            assert len(runs) == 2
            assert all(json.loads((p/'run.json').read_text())['reason'] == 'precheck_failed' for p in runs)
            before = instance.log_path.read_bytes()
            instance.command('l')
            assert instance.log_path.read_bytes() == before
            assert instance.run_log is None
            state = json.loads(instance.state_path.read_text())
            assert state['module_log_dir'].endswith('/fsd_modules')
        finally:
            instance.log.close()


def test_start_exception_returns_to_session_log(tmp_path):
    import manager
    with patch.object(manager, 'ROOT', tmp_path), patch.object(manager, 'RUNTIME', tmp_path):
        instance = Manager([], color=False)
        try:
            with patch.object(instance, 'permissions', side_effect=RuntimeError('injected')):
                instance.start()
            assert instance.run_log is None
            run = next((tmp_path/'wuta_logs/pending').iterdir())
            assert 'injected' in (run/'manager.log').read_text()
            assert instance.log_path == instance.session_log_path
        finally:
            instance.log.close()


def test_runtime_output_drained_before_archive(tmp_path):
    import manager
    with patch.object(manager, 'ROOT', tmp_path), patch.object(manager, 'RUNTIME', tmp_path):
        instance = Manager([], color=False)
        try:
            instance.run_log = RunLog.create(tmp_path, mission='acceleration')
            instance.log_dir = str(instance.run_log.path)
            instance.use_log(instance.run_log.path/'manager.log')
            instance.child = subprocess.Popen([sys.executable, '-c', 'print("unique-runtime-event")'],
                                             stdout=subprocess.PIPE, text=True)
            import threading
            instance.output_thread = threading.Thread(target=instance.read_output, args=(instance.child,))
            instance.output_thread.start()
            instance.child.wait()
            instance.pump()
            text = (Path(instance.log_dir)/'manager.log').read_text()
            assert text.count('unique-runtime-event') == 1
            assert Path(instance.log_dir).parent.name == 'acceleration'
            assert instance.run_log is None
        finally:
            instance.log.close()


def test_display_uses_authoritative_reasons_and_legacy_is_unknown():
    fields = 'lap=0 mode_selected=1 go_count=1 go_pending=1 lidar_ready=1 localization_ready=1'
    assert describe(1, 2, 0, fields + ' diag_version=2 wait=go')['下一步'] == '等待：本次任务GO'
    assert '未提供' in describe(1, 2, 0, fields)['下一步']
    assert '未知' in describe(1, 2, 0, 'lap=0')['门控']


def test_standalone_uses_vcu_mode_cache_mission(tmp_path, monkeypatch):
    import run_logged
    monkeypatch.setattr(run_logged, 'ROOT', tmp_path)
    monkeypatch.setattr(run_logged.mode_cache, 'read_mission',
                        lambda config: ({'mission': 'acceleration', 'vcu_mode': 2}, ''))
    monkeypatch.setenv('FSD_RUN_MODE', 'hardware')
    monkeypatch.setattr(sys, 'argv', ['run_logged', sys.executable, '-c', 'pass'])
    assert run_logged.main() == 0
    run = next((tmp_path/'wuta_logs/acceleration').iterdir())
    data = json.loads((run/'run.json').read_text())
    assert data['mission'] == 'acceleration'
    assert data['mission_source'] == 'vcu_mode_cache'
    assert data['vcu_mode'] == 2


def test_standalone_owner_logs_once_and_preserves_exit_code(tmp_path):
    root = Path(__file__).resolve().parents[1]
    code = '''import sys
from pathlib import Path
sys.path.insert(0, sys.argv[1])
import run_logged
run_logged.ROOT = Path(sys.argv[2])
sys.argv = ['run_logged', sys.executable, '-c', 'print("one-event"); raise SystemExit(17)']
raise SystemExit(run_logged.main())
'''
    result = subprocess.run([sys.executable, '-c', code, str(root/'tools'), str(tmp_path)],
                            capture_output=True, text=True, timeout=5)
    assert result.returncode == 17, result.stderr
    run = next((tmp_path/'wuta_logs/pending').iterdir())
    assert (run/'manager.log').read_text().count('one-event') == 1
    assert json.loads((run/'run.json').read_text())['exit_code'] == 17


def test_observer_exit_warns_without_failing_vehicle_groups(tmp_path):
    source = (Path(__file__).resolve().parents[1]/'start_full_fsd.sh').read_text()
    function = 'check_children() {' + source.split('check_children() {', 1)[1].split('\n}\n', 1)[0] + '\n}\n'
    result = subprocess.run(['bash', '-c', '''
set -Eeuo pipefail
OBSERVER_PIDS=(99999999)
CHILD_PIDS=()
report_child_failure() { exit 9; }
''' + function + 'check_children; check_children'], capture_output=True, text=True, timeout=5)
    assert result.returncode == 0
    assert result.stderr.count('只读任务监控退出') == 1


def test_standalone_preserves_controlling_terminal_and_ctrl_c(tmp_path):
    import os
    import pty
    import select
    import signal
    import time
    root = Path(__file__).resolve().parents[1]
    payload = '''import signal,time,sys
with open('/dev/tty', 'r'):
    pass
signal.signal(signal.SIGINT, lambda *_: sys.exit(0))
print('tty-ready', flush=True)
time.sleep(30)
'''
    helper = '''import sys
from pathlib import Path
sys.path.insert(0, sys.argv[1])
import run_logged
run_logged.ROOT=Path(sys.argv[2])
sys.argv=['run_logged', sys.executable, '-c', sys.argv[3]]
raise SystemExit(run_logged.main())
'''
    pid, terminal = pty.fork()
    if pid == 0:
        os.execv(sys.executable, [sys.executable, '-c', helper, str(root/'tools'), str(tmp_path), payload])
    reaped = False
    try:
        deadline = time.monotonic() + 5
        output = b''
        while b'tty-ready' not in output and time.monotonic() < deadline:
            if select.select([terminal], [], [], .1)[0]:
                output += os.read(terminal, 8192)
        assert b'tty-ready' in output, output
        os.write(terminal, b'\x03')
        while time.monotonic() < deadline:
            result, status = os.waitpid(pid, os.WNOHANG)
            if result:
                reaped = True
                assert os.waitstatus_to_exitcode(status) == 0
                break
            time.sleep(.02)
        assert reaped, output
        run = next((tmp_path/'wuta_logs/pending').iterdir())
        assert (run/'manager.log').read_text().count('tty-ready') == 1
        assert json.loads((run/'run.json').read_text())['exit_code'] == 0
    finally:
        if not reaped:
            os.killpg(pid, signal.SIGKILL)
            os.waitpid(pid, 0)
        os.close(terminal)


def test_manager_replaces_legacy_mode_selection_hint(tmp_path):
    import manager
    with patch.object(manager, 'ROOT', tmp_path), patch.object(manager, 'RUNTIME', tmp_path):
        instance = Manager([], color=False)
        try:
            instance.events.put('[状态 21:08:49] 任务选择：acceleration 直线加速')
            instance.events.put('[提示] 任务仍需满足就绪条件、由 VCU 选择模式，再按 RES GO。')
            instance.drain_events()
            text = instance.log_path.read_text()
            assert '任务选择：acceleration 直线加速' in text
            assert '任务监控最新的“任务选择”和“下一步”' in text
            assert '由 VCU 选择模式，再按 RES GO' not in text
        finally:
            instance.log.close()
