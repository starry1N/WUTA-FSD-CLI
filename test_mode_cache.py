from pathlib import Path

import pytest

import mode_cache


def boot_id():
    return Path('/proc/sys/kernel/random/boot_id').read_text().strip()


def write_cache(tmp_path, **overrides):
    values = dict(version=1, boot_id=boot_id(), session_id='test', pid=1,
                  process_start_ticks=1, iface='can0', can_id=0x501,
                  valid=0, mode=3, sequence=1)
    values.update(overrides)
    (tmp_path / 'can0.mode').write_text(
        ''.join(f'{key}={value}\n' for key, value in values.items()))


def test_missing_cache_is_reported(tmp_path):
    info, reason = mode_cache.read_mode_cache(tmp_path, 'can0')
    assert info is None
    assert reason == 'cache unavailable'


def test_invalid_interface_is_rejected(tmp_path):
    info, reason = mode_cache.read_mode_cache(tmp_path, '../can0')
    assert info is None
    assert reason == 'invalid interface'


def test_invalid_cache_format_is_rejected(tmp_path):
    (tmp_path / 'can0.mode').write_text('bad-line\n')
    info, reason = mode_cache.read_mode_cache(tmp_path, 'can0')
    assert info is None
    assert reason == 'invalid cache format'


def test_boot_mismatch_is_rejected(tmp_path):
    write_cache(tmp_path, boot_id='other-boot')
    info, reason = mode_cache.read_mode_cache(tmp_path, 'can0')
    assert info is None
    assert reason == 'cache boot mismatch'


def test_invalid_mode_is_not_used(tmp_path):
    write_cache(tmp_path, valid=0)
    info, reason = mode_cache.read_mode_cache(tmp_path, 'can0')
    assert info is None
    assert reason == 'cache has no valid mode'


def test_location_can_be_read_from_config(tmp_path, monkeypatch):
    monkeypatch.delenv('CAN_IFACE', raising=False)
    config = tmp_path / 'can_interface.yaml'
    config.write_text('''can_interface:
  ros__parameters:
    can:
      device: can1
    mode_cache:
      directory: /run/custom
''')
    directory, iface = mode_cache.resolve_location(config)
    assert directory == '/run/custom'
    assert iface == 'can1'
