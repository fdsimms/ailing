import asyncio
from pathlib import Path

import httpx
import pytest

from ailing.tts import OUTPUT_FORMAT, AudioCache, TtsFailed, azure_synthesize, ssml


def test_ssml_names_the_voice_and_escapes_the_text() -> None:
    out = ssml("A & B <ok>", "th-TH-NiwatNeural")
    assert '<voice name="th-TH-NiwatNeural">A &amp; B &lt;ok&gt;</voice>' in out
    assert out.startswith("<speak version='1.0' xml:lang='th-TH'>")


def run(handler: httpx.MockTransport, text: str = "สวัสดีครับ") -> bytes:
    async def go() -> bytes:
        async with httpx.AsyncClient(transport=handler) as client:
            return await azure_synthesize("k", "eastus", client)(text, "th-TH-NiwatNeural")

    return asyncio.run(go())


def test_posts_ssml_to_the_regional_endpoint_with_the_key_and_format() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, content=b"ID3mp3")

    assert run(httpx.MockTransport(handler)) == b"ID3mp3"
    request = seen[0]
    assert str(request.url) == "https://eastus.tts.speech.microsoft.com/cognitiveservices/v1"
    assert request.headers["Ocp-Apim-Subscription-Key"] == "k"
    assert request.headers["X-Microsoft-OutputFormat"] == OUTPUT_FORMAT
    assert request.headers["Content-Type"] == "application/ssml+xml"
    assert "สวัสดีครับ" in request.content.decode()


def test_an_error_status_is_tts_failed() -> None:
    transport = httpx.MockTransport(lambda r: httpx.Response(401, text="bad key"))
    with pytest.raises(TtsFailed, match="401"):
        run(transport)


def test_an_empty_body_is_tts_failed() -> None:
    with pytest.raises(TtsFailed):
        run(httpx.MockTransport(lambda r: httpx.Response(200, content=b"")))


def test_a_network_error_is_tts_failed() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("down")

    with pytest.raises(TtsFailed, match="Couldn't reach Azure"):
        run(httpx.MockTransport(handler))


def test_cache_writes_whole_files(tmp_path: Path) -> None:
    cache = AudioCache(tmp_path)
    assert not cache.has(3, 0)
    cache.write(3, 0, b"mp3")
    assert cache.has(3, 0)
    assert cache.path(3, 0).read_bytes() == b"mp3"
    assert list((tmp_path / "3").iterdir()) == [cache.path(3, 0)]
