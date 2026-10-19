from pathlib import Path

from ailing.config import SECRET_NAMES, load


def test_defaults_without_environment() -> None:
    settings = load({})
    assert settings.db_path == Path("ailing.db")
    assert settings.missing() == list(SECRET_NAMES)


def test_reads_paths_and_secrets() -> None:
    settings = load(
        {"AILING_DB_PATH": "/data/ailing.db", "ANTHROPIC_API_KEY": "k", "ANKIMCP_URL": ""}
    )
    assert settings.db_path == Path("/data/ailing.db")
    assert settings.secrets == {"ANTHROPIC_API_KEY": "k"}
    assert "ANKIMCP_URL" in settings.missing()
