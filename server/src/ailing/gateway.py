"""The one door to Anki. Every call goes through `with_timeout`, because the AnkiMCP tunnel hangs
rather than errors when Anki is unreachable.

Everything above the gateway is written against `CallTool`; the real one is the MCP client in
`ankimcp.py`, and tests pass fakes.
"""

import asyncio
from collections.abc import Callable, Coroutine
from typing import Any

TIMEOUT_SECONDS = 45.0

# Calls one AnkiMCP tool by name and returns its parsed JSON result.
CallTool = Callable[[str, dict[str, Any]], Coroutine[Any, Any, dict[str, Any]]]


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
            raise AnkiUnavailable(f"{name} failed: {describe(e)}") from e

    return timed


def describe(error: BaseException) -> str:
    """What went wrong, in a sentence. The MCP client runs in task groups, so its real error (a bad
    token, a refused connection) arrives wrapped in exception groups whose own text is only
    "unhandled errors in a TaskGroup"; this reads the errors inside instead."""
    if isinstance(error, BaseExceptionGroup):
        return "; ".join(describe(inner) for inner in error.exceptions)
    kind = type(error).__name__
    return f"{kind}: {error}" if str(error) else kind
