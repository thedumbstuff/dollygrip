import os

from dollygrip import discovery


def test_env_overrides_win(monkeypatch):
    monkeypatch.setenv("RESOLVE_SCRIPT_API", "/custom/api")
    monkeypatch.setenv("RESOLVE_SCRIPT_LIB", "/custom/lib/fusionscript.so")
    paths = discovery.resolved_paths()
    assert paths.api_root == "/custom/api"
    assert paths.lib_path == "/custom/lib/fusionscript.so"
    assert paths.modules_dir == os.path.join("/custom/api", "Modules")


def test_defaults_have_modules_dir():
    paths = discovery.default_paths()
    assert paths.modules_dir.endswith("Modules")
    assert paths.api_root in paths.modules_dir


def test_probe_never_raises(monkeypatch):
    monkeypatch.setenv("RESOLVE_SCRIPT_API", "/definitely/not/here")
    monkeypatch.setenv("RESOLVE_SCRIPT_LIB", "/definitely/not/here/lib.so")
    info = discovery.probe()
    assert info["modules_dir_exists"] is False
    assert isinstance(info, dict)
