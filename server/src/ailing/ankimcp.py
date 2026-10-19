"""AnkiMCP as a plain MCP client: the gateway's `CallTool`, with no Claude in between.

Each call opens a session, calls one tool and closes it. The snapshot is about a dozen calls a day,
so a long-lived connection isn't worth keeping alive through a tunnel that hangs. Every call goes
through `with_timeout` (45 seconds).

Authentication is a bearer token when ANKIMCP_TOKEN is set. How ankimcp.ai actually authenticates a
client that isn't Claude couldn't be checked from the build sandbox; if it needs something else
(another header, OAuth), this is the one place to change.
"""

import json
from typing import Any

import httpx2
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client
from mcp.types import CallToolResult, TextContent

from ailing.gateway import TIMEOUT_SECONDS, AnkiUnavailable, CallTool, with_timeout


def ankimcp_call_tool(url: str, token: str | None, seconds: float = TIMEOUT_SECONDS) -> CallTool:
    headers = {"Authorization": f"Bearer {token}"} if token else {}

    async def call(name: str, args: dict[str, Any]) -> dict[str, Any]:
        async with (
            httpx2.AsyncClient(headers=headers, timeout=seconds) as http,
            streamable_http_client(url, http_client=http) as (read, write),
            ClientSession(read, write) as session,
        ):
            await session.initialize()
            result = await session.call_tool(name, args)
        return parse_result(name, result)

    return with_timeout(call, seconds)


def parse_result(name: str, result: object) -> dict[str, Any]:
    """A tool's result as a dict. AnkiMCP's results arrive as JSON text, so the first text block is
    read first; structured content is the fallback, unwrapping the `{"result": ...}` an MCP server
    puts around a tool that returns a plain value."""
    if not isinstance(result, CallToolResult):
        raise AnkiUnavailable(f"{name} returned an unexpected result: {type(result).__name__}")
    text = next((c.text for c in result.content if isinstance(c, TextContent)), None)
    if result.is_error:
        raise AnkiUnavailable(f"{name} failed: {text or 'no details'}")
    parsed = _json_object(text)
    if parsed is not None:
        return parsed
    structured = result.structured_content
    if isinstance(structured, dict):
        inner = structured.get("result") if set(structured) == {"result"} else structured
        if isinstance(inner, dict):
            return inner
        if isinstance(inner, str) and (unwrapped := _json_object(inner)) is not None:
            return unwrapped
    if text is None:
        raise AnkiUnavailable(f"{name} returned no text")
    raise AnkiUnavailable(f"{name} returned something that isn't a JSON object: {text[:200]}")


def _json_object(text: str | None) -> dict[str, Any] | None:
    if text is None:
        return None
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None
