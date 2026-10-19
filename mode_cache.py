"""Read the ZLG bridge VCU mode cache before ROS starts.

Only used to classify the run directory; mission_manager remains the
authoritative mission state owner.
"""
import os
from pathlib import Path
import stat

DEFAULT_IFACE = 'can0'
DEFAULT_DIRECTORY = '/run/zlgcan_bridge'
DEFAULT_CAN_ID = 0x501
MISSIONS = {2: 'acceleration', 3: 'trackdrive', 4: 'skidpad',
            5: 'ebs_test', 6: 'inspection'}


def _regular_text(path):
    try:
        info = os.lstat(path)
        if not stat.S_ISREG(info.st_mode) or info.st_size > 4096:
            return None
        return Path(path).read_text()
    except OSError:
        return None


def _start_ticks(pid):
    try:
        text = Path(f'/proc/{pid}/stat').read_text()
    except OSError:
        return None
    end = text.rfind(')')
    if end < 0:
        return None
    fields = text[end + 2:].split()
    # /proc/<pid>/stat: state is field 3, starttime is field 22.
    return int(fields[19]) if len(fields) >= 20 else None


def _valid_iface(iface):
    return (iface and iface not in ('.', '..') and len(iface) <= 63
            and all(c.isalnum() or c in '_-.' for c in iface))


def read_mode_cache(directory=DEFAULT_DIRECTORY, iface=DEFAULT_IFACE,
                    can_id=DEFAULT_CAN_ID):
    """Return (info, reason); info is None when the cache is not usable."""
    if not _valid_iface(iface):
        return None, 'invalid interface'
    path = Path(directory) / f'{iface}.mode'
    text = _regular_text(path)
    if text is None:
        return None, 'cache unavailable'
    values = {}
    for line in text.splitlines():
        key, separator, value = line.partition('=')
        if not separator or key in values:
            return None, 'invalid cache format'
        values[key] = value
    try:
        if values['version'] != '1':
            return None, 'unsupported cache version'
        boot_id = Path('/proc/sys/kernel/random/boot_id').read_text().strip()
        if values['boot_id'] != boot_id:
            return None, 'cache boot mismatch'
        if values['iface'] != iface:
            return None, 'cache interface mismatch'
        if int(values['can_id']) != can_id:
            return None, 'cache CAN id mismatch'
        if int(values['valid']) != 1:
            return None, 'cache has no valid mode'
        pid = int(values['pid'])
        ticks = int(values['process_start_ticks'])
        sequence = int(values['sequence'])
        mode = int(values['mode'])
        if pid <= 0 or ticks <= 0 or sequence <= 0:
            return None, 'invalid cache value'
        if _start_ticks(pid) != ticks:
            return None, 'bridge process unavailable'
        comm = Path(f'/proc/{pid}/comm').read_text().strip()
        if comm != 'zlg_can_bridge':
            return None, 'not a bridge process'
    except (KeyError, OSError, ValueError):
        return None, 'invalid or inaccessible cache'
    mission = MISSIONS.get(mode)
    if mission is None:
        return None, f'unsupported VCU mode {mode}'
    return {'mission': mission, 'vcu_mode': mode, 'sequence': sequence,
            'session_id': values['session_id']}, ''


def resolve_location(config_path=None):
    """Resolve cache directory and CAN interface from env/config/defaults."""
    directory = DEFAULT_DIRECTORY
    iface = os.environ.get('CAN_IFACE') or DEFAULT_IFACE
    if config_path:
        try:
            import yaml
            document = yaml.safe_load(Path(config_path).read_text()) or {}
            parameters = document.get('can_interface', {}).get('ros__parameters', {})
            if not os.environ.get('CAN_IFACE'):
                iface = parameters.get('can', {}).get('device', iface)
            directory = parameters.get('mode_cache', {}).get('directory', directory)
        except (OSError, ValueError, AttributeError):
            pass
    return directory, iface


def read_mission(config_path=None):
    """Return (mode cache info, reason) using the configured cache location."""
    directory, iface = resolve_location(config_path)
    return read_mode_cache(directory, iface)
