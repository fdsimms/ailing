"""Text to speech: one MP3 per line, made once at normal speed and cached on the volume. Slower
playback is the player's rate on the phone (docs/architecture.md, Audio), so there's one file per
line whatever speed is chosen.

Azure's REST API, as far as it could be checked from the sandbox (learn.microsoft.com didn't
resolve): the host (`https://{region}.tts.speech.microsoft.com`), the `Ocp-Apim-Subscription-Key`
header and the `audio-24khz-48kbitrate-mono-mp3` format name are confirmed against Microsoft's own
Speech SDK source. The `/cognitiveservices/v1` path, the `X-Microsoft-OutputFormat` header and the
voice names are from memory and unverified until the first real call; the voices can be changed
with AZURE_VOICE_A and AZURE_VOICE_B without a code change.
"""

from collections.abc import Callable, Coroutine
from pathlib import Path
from typing import Any
from xml.sax.saxutils import escape, quoteattr

import httpx

DEFAULT_VOICES = {"A": "th-TH-NiwatNeural", "B": "th-TH-PremwadeeNeural"}
OUTPUT_FORMAT = "audio-24khz-48kbitrate-mono-mp3"
TIMEOUT_SECONDS = 30.0

# Speaks one line in one voice and returns the MP3 bytes.
Synthesize = Callable[[str, str], Coroutine[Any, Any, bytes]]


class TtsFailed(Exception):
    """Azure didn't return audio. The text is still served, without audio for that line."""


def ssml(text: str, voice: str) -> str:
    return (
        "<speak version='1.0' xml:lang='th-TH'>"
        f"<voice name={quoteattr(voice)}>{escape(text)}</voice>"
        "</speak>"
    )


def azure_synthesize(key: str, region: str, client: httpx.AsyncClient) -> Synthesize:
    url = f"https://{region}.tts.speech.microsoft.com/cognitiveservices/v1"

    async def synthesize(text: str, voice: str) -> bytes:
        try:
            response = await client.post(
                url,
                content=ssml(text, voice).encode(),
                headers={
                    "Ocp-Apim-Subscription-Key": key,
                    "Content-Type": "application/ssml+xml",
                    "X-Microsoft-OutputFormat": OUTPUT_FORMAT,
                    "User-Agent": "ailing",
                },
                timeout=TIMEOUT_SECONDS,
            )
        except httpx.HTTPError as e:
            raise TtsFailed(f"Couldn't reach Azure: {e}") from e
        if response.status_code != 200 or not response.content:
            raise TtsFailed(f"Azure answered {response.status_code}: {response.text[:200]}")
        return response.content

    return synthesize


class AudioCache:
    """`<dir>/<text id>/<line index>.mp3`. A file is written whole or not at all."""

    def __init__(self, root: Path) -> None:
        self.root = root

    def path(self, text_id: int, line: int) -> Path:
        return self.root / str(text_id) / f"{line}.mp3"

    def has(self, text_id: int, line: int) -> bool:
        return self.path(text_id, line).is_file()

    def write(self, text_id: int, line: int, audio: bytes) -> None:
        path = self.path(text_id, line)
        path.parent.mkdir(parents=True, exist_ok=True)
        partial = path.with_suffix(".part")
        partial.write_bytes(audio)
        partial.replace(path)
