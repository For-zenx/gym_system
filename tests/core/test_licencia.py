import importlib.util
import json
import sys
from datetime import date
from pathlib import Path

import pytest

_CONFIG_DIR = Path(__file__).resolve().parents[2] / "config"
if "config.licencia" in sys.modules:
    del sys.modules["config.licencia"]

_spec = importlib.util.spec_from_file_location(
    "config.licencia",
    _CONFIG_DIR / "licencia.py",
)
licencia = importlib.util.module_from_spec(_spec)
sys.modules["config.licencia"] = licencia
_spec.loader.exec_module(licencia)

TEST_MACHINE = "TEST-MACHINE-075"
TEST_GYM = "Gym Test"


@pytest.fixture
def license_env(tmp_path, monkeypatch):
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    monkeypatch.setenv("PERFECTLINE_ROOT", str(tmp_path))
    monkeypatch.setenv("DJANGO_SETTINGS_MODULE", "config.settings_production")
    monkeypatch.setattr(licencia, "get_machine_id", lambda: TEST_MACHINE)
    return config_dir


@pytest.fixture
def mock_registry(monkeypatch):
    state = {"locked": False, "machine_id": None}

    def is_expiry_locked(machine_id=None):
        mid = machine_id or licencia.get_machine_id()
        return state["locked"] and state["machine_id"] == mid

    def set_expiry_lock(machine_id=None):
        state["locked"] = True
        state["machine_id"] = machine_id or licencia.get_machine_id()

    def clear_expiry_lock():
        state["locked"] = False
        state["machine_id"] = None

    monkeypatch.setattr(licencia, "is_expiry_locked", is_expiry_locked)
    monkeypatch.setattr(licencia, "set_expiry_lock", set_expiry_lock)
    monkeypatch.setattr(licencia, "clear_expiry_lock", clear_expiry_lock)
    return state


def write_license(config_dir, expires_on="2099-12-31", machine_id=TEST_MACHINE, nombre=TEST_GYM, signature=None):
    if signature is None:
        signature = licencia.compute_signature(machine_id, nombre, expires_on)
    data = {
        "machine_id": machine_id,
        "nombre": nombre,
        "expires_on": expires_on,
        "signature": signature,
    }
    path = config_dir / "license.dat"
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def test_compute_signature_with_and_without_expiry():
    with_expiry = licencia.compute_signature("ABC", "Gym", "2027-06-18")
    without_expiry = licencia.compute_signature("ABC", "Gym", None)
    assert with_expiry != without_expiry
    assert len(with_expiry) == 64


def test_verify_license_file_valid(license_env):
    data = json.loads(write_license(license_env).read_text(encoding="utf-8"))
    ok, error = licencia.verify_license_file(data, machine_id=TEST_MACHINE)
    assert ok is True
    assert error is None


def test_verify_license_file_wrong_machine(license_env):
    write_license(license_env)
    data = licencia.load_license_data(license_env / "license.dat")
    ok, error = licencia.verify_license_file(data, machine_id="OTHER-PC")
    assert ok is False
    assert "no es valida para este hardware" in error


def test_verify_license_file_tampered_signature(license_env):
    write_license(license_env, signature="deadbeef")
    data = licencia.load_license_data(license_env / "license.dat")
    ok, error = licencia.verify_license_file(data, machine_id=TEST_MACHINE)
    assert ok is False
    assert "alterado" in error


def test_verify_license_file_legacy_without_expires_on(license_env):
    legacy_sig = licencia.compute_signature(TEST_MACHINE, TEST_GYM, None)
    data = {
        "machine_id": TEST_MACHINE,
        "nombre": TEST_GYM,
        "signature": legacy_sig,
    }
    (license_env / "license.dat").write_text(json.dumps(data), encoding="utf-8")
    ok, error = licencia.verify_license_file(data, machine_id=TEST_MACHINE)
    assert ok is True
    assert error is None


def test_license_is_required__skip_overrides_production(monkeypatch):
    """SKIP_LICENSE_CHECK disables enforcement even under settings_production."""
    monkeypatch.setenv("DJANGO_SETTINGS_MODULE", "config.settings_production")
    monkeypatch.setenv("LICENSE_REQUIRED", "False")
    monkeypatch.setenv("SKIP_LICENSE_CHECK", "true")
    assert licencia.license_is_required() is False


def test_license_is_required_respects_dev_env(monkeypatch):
    monkeypatch.setenv("DJANGO_SETTINGS_MODULE", "config.settings")
    monkeypatch.setenv("LICENSE_REQUIRED", "False")
    monkeypatch.delenv("SKIP_LICENSE_CHECK", raising=False)
    assert licencia.license_is_required() is False


def test_get_license_status_offline_does_not_expire(license_env, mock_registry, monkeypatch):
    write_license(license_env, expires_on="2020-01-01")
    monkeypatch.setattr(licencia, "fetch_network_date_utc", lambda: None)

    status = licencia.get_license_status()

    assert status["status"] == licencia.STATUS_VALID
    assert status["warning"] is False
    assert mock_registry["locked"] is False


def test_get_license_status_online_expired_sets_lock(license_env, mock_registry, monkeypatch):
    write_license(license_env, expires_on="2026-06-18")
    monkeypatch.setattr(licencia, "fetch_network_date_utc", lambda: date(2026, 6, 19))

    status = licencia.get_license_status()

    assert status["status"] == licencia.STATUS_EXPIRED
    assert mock_registry["locked"] is True


def test_get_license_status_expiry_locked_blocks_offline(license_env, mock_registry, monkeypatch):
    write_license(license_env, expires_on="2025-01-01")
    mock_registry["locked"] = True
    mock_registry["machine_id"] = TEST_MACHINE
    monkeypatch.setattr(licencia, "fetch_network_date_utc", lambda: None)

    status = licencia.get_license_status()

    assert status["status"] == licencia.STATUS_EXPIRY_LOCKED


def test_get_license_status_renewed_license_clears_lock(license_env, mock_registry, monkeypatch):
    mock_registry["locked"] = True
    mock_registry["machine_id"] = TEST_MACHINE
    write_license(license_env, expires_on="2099-12-31")
    monkeypatch.setattr(licencia, "fetch_network_date_utc", lambda: date(2026, 6, 18))

    status = licencia.get_license_status()

    assert status["status"] == licencia.STATUS_VALID
    assert mock_registry["locked"] is False


def test_get_license_status_warning_within_14_days(license_env, mock_registry, monkeypatch):
    write_license(license_env, expires_on="2026-07-02")
    monkeypatch.setattr(licencia, "fetch_network_date_utc", lambda: date(2026, 6, 18))

    status = licencia.get_license_status()

    assert status["status"] == licencia.STATUS_VALID
    assert status["warning"] is True
    assert "vence el" in status["message"]


def test_verify_license_exits_when_invalid(license_env, monkeypatch):
    monkeypatch.setenv("DJANGO_SETTINGS_MODULE", "config.settings_production")

    with pytest.raises(SystemExit):
        licencia.verify_license()
