"""The AnkiMCP client against a real MCP server over streamable HTTP, serving AnkiMCP's tool shapes
from the fake deck, behind a bearer token."""

import asyncio
import json
import socket
import threading
import time
from collections.abc import Iterator
from typing import Any

import pytest
import uvicorn
from fake_anki import FakeAnki, card, note
from mcp.server.mcpserver import MCPServer
from mcp.types import CallToolResult, TextContent

from ailing.ankimcp import ankimcp_call_tool, parse_result
from ailing.gateway import AnkiUnavailable
from ailing.lexicon import fetch_snapshot

TOKEN = "deck-token"
ANKI = FakeAnki(
    [note(1, "ฉัน", "I; me"), note(2, "รับอะไรดี", "what would you like?")],
    [card(1, 2, 300), card(2, 2, 5, due=True)],
)


def build_server() -> MCPServer:
    server = MCPServer("fake-ankimcp")

    # AnkiMCP answers with JSON text, so these return strings rather than structured content.
    @server.tool()
    async def find_notes(query: str, limit: int = 100, offset: int = 0) -> str:
        return json.dumps(
            await ANKI("find_notes", {"query": query, "limit": limit, "offset": offset})
        )

    @server.tool()
    async def notes_info(notes: list[int], include_fields: list[str] | None = None) -> str:
        return json.dumps(await ANKI("notes_info", {"notes": notes}))

    @server.tool()
    async def cards_stats(deck: str, limit: int = 1000, offset: int = 0) -> str:
        return json.dumps(
            await ANKI("cards_stats", {"deck": deck, "limit": limit, "offset": offset})
        )

    @server.tool()
    async def hangs() -> str:
        await asyncio.sleep(30)
        return "{}"

    return server


def with_bearer(app: Any) -> Any:
    async def guarded(scope: dict[str, Any], receive: Any, send: Any) -> None:
        if scope["type"] == "http":
            headers = dict(scope["headers"])
            if headers.get(b"authorization") != f"Bearer {TOKEN}".encode():
                await send({"type": "http.response.start", "status": 401, "headers": []})
                await send({"type": "http.response.body", "body": b"unauthorized"})
                return
        await app(scope, receive, send)

    return guarded


@pytest.fixture(scope="module")
def url() -> Iterator[str]:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    app = with_bearer(build_server().streamable_http_app())
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.time() + 10
    while not server.started and time.time() < deadline:
        time.sleep(0.05)
    yield f"http://127.0.0.1:{port}/mcp"
    server.should_exit = True
    thread.join(timeout=5)


def test_calls_a_tool_and_reads_its_json(url: str) -> None:
    call = ankimcp_call_tool(url, TOKEN)
    result = asyncio.run(call("find_notes", {"query": "deck:x", "limit": 10, "offset": 0}))
    assert result["noteIds"] == [1, 2]
    assert result["hasMore"] is False


def test_the_whole_snapshot_runs_over_mcp(url: str) -> None:
    entries = asyncio.run(fetch_snapshot(ankimcp_call_tool(url, TOKEN)))
    assert [(e.text, e.tier, e.due) for e in entries] == [
        ("ฉัน", "mature", False),
        ("รับอะไรดี", "young", True),
    ]


def test_a_wrong_token_is_anki_unavailable(url: str) -> None:
    with pytest.raises(AnkiUnavailable):
        asyncio.run(ankimcp_call_tool(url, "wrong")("find_notes", {"query": "x"}))


def test_a_hanging_tool_times_out(url: str) -> None:
    with pytest.raises(AnkiUnavailable, match="took longer than"):
        asyncio.run(ankimcp_call_tool(url, TOKEN, seconds=0.5)("hangs", {}))


def test_nothing_listening_is_anki_unavailable() -> None:
    with pytest.raises(AnkiUnavailable):
        asyncio.run(ankimcp_call_tool("http://127.0.0.1:9/mcp", TOKEN, seconds=5)("x", {}))


def result(text: str, error: bool = False, structured: Any = None) -> CallToolResult:
    return CallToolResult(
        content=[TextContent(type="text", text=text)], is_error=error, structured_content=structured
    )


def test_parse_result_reads_json_text_then_structured_content() -> None:
    assert parse_result("t", result('{"b": 2}', structured={"result": '{"b": 2}'})) == {"b": 2}
    assert parse_result("t", result("summary", structured={"a": 1})) == {"a": 1}
    assert parse_result("t", result("summary", structured={"result": {"c": 3}})) == {"c": 3}
    assert parse_result("t", result("summary", structured={"result": '{"d": 4}'})) == {"d": 4}


@pytest.mark.parametrize(
    ("res", "match"),
    [
        (result("Anki is not running", error=True), "Anki is not running"),
        (result("not json"), "isn't a JSON object"),
        (result("[1, 2]"), "isn't a JSON object"),
        ("not a result", "unexpected result"),
    ],
)
def test_parse_result_explains_what_went_wrong(res: object, match: str) -> None:
    with pytest.raises(AnkiUnavailable, match=match):
        parse_result("find_notes", res)
