"""The one door to Anki. Every call goes through `with_timeout`, because the AnkiMCP tunnel hangs
rather than errors when Anki is unreachable.

The MCP client itself (a session against ANKIMCP_URL) isn't here yet: it waits on the endpoint and
credential (docs/anki-spike.md, "Still needed"). Everything above it is written against `CallTool`,
so it slots in without changing the callers.
"""

import asyncio
from collections.abc import Awaitable, Callable
from typing import Any

TIMEOUT_SECONDS = 45.0

# Calls one AnkiMCP tool by name and returns its parsed JSON result.
CallTool = Callable[[str, dict[str, Any]], Awaitable[dict[str, Any]]]


class AnkiUnavailable(Exception):
    """Anki didn't answer in time, or the call failed. Callers fall back to the last snapshot."""


def with_timeout(call: CallTool, seconds: float = TIMEOUT_SECONDS) -> CallTool:
    async def timed(name: str, args: dict[str, Any]) -> dict[str, Any]:
        try:
            return await asyncio.wait_for(call(name, args), timeout=seconds)
        except TimeoutError as e:
            raise AnkiUnavailable(f"{name} took longer than {seconds:g} seconds") from e
        except AnkiUnavailable:
            raise
        except Exception as e:
            raise AnkiUnavailable(f"{name} failed: {e}") from e

    return timed
