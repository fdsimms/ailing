"""Server settings, all from the environment. Secrets are set with `fly secrets set` and never
reach the app on the phone; docs/deploy.md lists them."""

import os
from dataclasses import dataclass
from pathlib import Path

from ailing.tts import DEFAULT_VOICES

# Names of the secrets the server reads. Missing ones are allowed at startup, so the server can be
# deployed and health-checked before every key exists; the feature that needs one says so.
SECRET_NAMES = (
    "ANTHROPIC_API_KEY",
    "AZURE_SPEECH_KEY",
    "AZURE_SPEECH_REGION",
    "ANKIMCP_URL",
    "ANKIMCP_TOKEN",
    "APP_PASSPHRASE",
)


@dataclass(frozen=True)
class Settings:
    db_path: Path
    audio_dir: Path
    voices: dict[str, str]
    secrets: dict[str, str]

    def missing(self) -> list[str]:
        return [name for name in SECRET_NAMES if not self.secrets.get(name)]


def load(env: dict[str, str] | None = None) -> Settings:
    env = dict(os.environ) if env is None else env
    return Settings(
        db_path=Path(env.get("AILING_DB_PATH", "ailing.db")),
        audio_dir=Path(env.get("AILING_AUDIO_DIR", "audio")),
        voices={
            "A": env.get("AZURE_VOICE_A") or DEFAULT_VOICES["A"],
            "B": env.get("AZURE_VOICE_B") or DEFAULT_VOICES["B"],
        },
        secrets={name: env[name] for name in SECRET_NAMES if env.get(name)},
    )
