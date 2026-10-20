"""Portable log catalog and driver progress checks; no Manager/Linux imports."""
from pathlib import Path
import re
import sys

sys.path.insert(0, str(Path(__file__).parent))
from dashboard import component_log_files, tail
from runtime_checks import RuntimeChecks, PROCESS_NAMES


def test_all_log_groups_and_run_change(tmp_path):
    names = ('fsd_modules/control/controller.log', 'external_log/perception_drivers.log',
             'external_log/visualization.log', 'chcnav_log/stamp/driver.log',
             'zlgCAN_log/bridge.log')
    state = {}
    previous = None
    for run_name in ('first', 'second'):
        root = tmp_path / run_name
        for name in names:
            path = root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes((run_name + ' 完整日志\n').encode('utf-8'))
        (root / 'configs').mkdir()
        (root / 'configs/not_component.log').write_text('excluded', encoding='utf-8')
        state.update(log_dir=str(root), module_log_dir=str(root / 'fsd_modules'))
        catalog = component_log_files(state)
        assert len(catalog) == len(names)
        assert {label.replace('\\', '/') for label, _ in catalog} == set(names)
        assert all(tail(path) == run_name + ' 完整日志\n' for _, path in catalog)
        if previous is not None:
            # Same labels, different absolute paths: selection must refresh to the new run.
            assert catalog != previous
        previous = catalog


def test_legacy_log_catalog_and_no_run(tmp_path):
    folder = tmp_path / 'legacy/modules'
    folder.mkdir(parents=True)
    (folder / 'chcnav.log').write_text('old', encoding='utf-8')
    state = {'log_dir': str(folder.parent), 'module_log_dir': str(folder)}
    assert len(component_log_files(state)) == 1
    assert component_log_files({}) == []
    assert component_log_files({'log_dir': str(tmp_path / 'gone')}) == []


def test_driver_group_catalog_and_independent_sensor_verification():
    source = (Path(__file__).resolve().parents[1] / 'start_full_fsd.sh').read_text(encoding='utf-8')
    launched = set(re.findall(r'^\s*start_group (\w+) ', source, re.M))
    assert launched == set(PROCESS_NAMES)
    progress = RuntimeChecks({})
    progress.consume('[启动] ZED / M1 驱动组 ...')
    assert progress.rows['process:perception_drivers']['status'] == '启动中'
    progress.consume('[成功] ZED / M1 驱动组：进程已启动（PID=123）')
    assert progress.rows['process:perception_drivers']['ok'] is True
    assert progress.rows['topic:M1 激光雷达数据']['ok'] is None
    progress.consume('[成功] M1 激光雷达数据：已收到 /rslidar_points 消息')
    assert progress.rows['topic:M1 激光雷达数据']['ok'] is True
    assert progress.rows['topic:ZED 相机图像']['ok'] is None
    progress.consume('[失败] ZED / M1 驱动组 进程已退出（PID=123）')
    assert progress.rows['process:perception_drivers']['ok'] is False
    assert RuntimeChecks({'build-only': True}).rows['process:perception_drivers']['status'] == '跳过'
    assert RuntimeChecks({'sensor-only': True}).rows['process:perception_drivers']['status'] != '跳过'
