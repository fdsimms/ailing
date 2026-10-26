"""What the gateway says when a call fails. The MCP client runs in task groups, so the real error
reaches it wrapped in exception groups."""

import asyncio
from typing import Any

import pytest

from ailing.gateway import AnkiUnavailable, describe, with_timeout


def failing(error: BaseException) -> Any:
    async def call(name: str, args: dict[str, Any]) -> dict[str, Any]:
        raise error

    return with_timeout(call)


def test_a_wrapped_error_is_reported_by_its_real_message() -> None:
    inner = ExceptionGroup("unhandled errors in a TaskGroup", [PermissionError("bad token")])
    wrapped = ExceptionGroup("unhandled errors in a TaskGroup", [inner])

    with pytest.raises(AnkiUnavailable) as caught:
        asyncio.run(failing(wrapped)("find_notes", {}))

    assert str(caught.value) == "find_notes failed: PermissionError: bad token"


def test_several_wrapped_errors_are_all_reported() -> None:
    group = ExceptionGroup("g", [ConnectionError("refused"), ValueError("bad reply")])

    assert describe(group) == "ConnectionError: refused; ValueError: bad reply"


def test_an_error_with_no_text_is_reported_by_its_type() -> None:
    assert describe(ConnectionResetError()) == "ConnectionResetError"
