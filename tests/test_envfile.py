import pytest

from dollygrip import envfile


def test_parse_handles_comments_quotes_export():
    text = "\n".join(
        [
            "# comment",
            "PEXELS_API_KEY=abc123",
            'export PIXABAY_API_KEY = "quoted value"',
            "COVERR_API_KEY='single'",
            "DOLLYGRIP_MEDIA_DIR=D:/stock # trailing comment",
            "BROKEN LINE WITHOUT EQUALS",
            "=novalue",
        ]
    )
    assert envfile.parse(text) == {
        "PEXELS_API_KEY": "abc123",
        "PIXABAY_API_KEY": "quoted value",
        "COVERR_API_KEY": "single",
        "DOLLYGRIP_MEDIA_DIR": "D:/stock",
    }


def test_load_prefers_existing_env_and_reports_file(tmp_path):
    f = tmp_path / ".env"
    f.write_text("PEXELS_API_KEY=fromfile\nPIXABAY_API_KEY=px\n", encoding="utf-8")
    env = {"PEXELS_API_KEY": "fromshell"}
    used = envfile.load(str(f), env=env)
    assert used == f and env == {"PEXELS_API_KEY": "fromshell", "PIXABAY_API_KEY": "px"}


def test_load_searches_cwd_then_explicit_env_var(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("DOLLYGRIP_ENV_FILE", raising=False)
    env = {}
    (tmp_path / ".env").write_text("COVERR_API_KEY=cwd\n", encoding="utf-8")
    assert envfile.load(env=env) == tmp_path / ".env" and env["COVERR_API_KEY"] == "cwd"
    (tmp_path / "other.env").write_text("COVERR_API_KEY=explicit\n", encoding="utf-8")
    monkeypatch.setenv("DOLLYGRIP_ENV_FILE", str(tmp_path / "other.env"))
    env = {}
    assert envfile.load(env=env).name == "other.env" and env["COVERR_API_KEY"] == "explicit"


def test_missing_explicit_file_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        envfile.load(str(tmp_path / "nope.env"), env={})


def test_stock_client_sees_env_file_keys(tmp_path):
    from dollygrip.stock import StockClient

    env = {}
    (tmp_path / ".env").write_text("PEXELS_API_KEY=k-from-file\nPIXABAY_API_KEY=\n", encoding="utf-8")
    envfile.load(str(tmp_path / ".env"), env=env)
    client = StockClient(media_dir=tmp_path, env=env)
    assert client.providers() == {"pexels": True, "pixabay": False, "coverr": False}  # empty value = no key
