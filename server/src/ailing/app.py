"""The HTTP API the iOS app calls. Every /api route needs the passphrase as a bearer token
(docs/architecture.md, Hosting); /health doesn't, so Fly can check the machine.

    GET   /api/check                  204 if the passphrase is right
    GET   /api/topics                 topics with their state and ready count; tops up in the background
    POST  /api/topics                 {name, favorite?} adds a topic (or returns the existing one)
    PATCH /api/topics/{id}            {favorite}
    POST  /api/topics/{id}/next       the next text for a topic; 202 {"writing": true} while one is
                                      being written in the background, so ask again shortly
    GET   /api/settings               {stretch_words: "topic" | "any"}
    PATCH /api/settings               the same fields; takes effect from the next text written
    POST  /api/texts/{id}/reading     logs a session with a text and adjusts difficulty
    GET   /api/texts/{id}/lines/{n}/audio   one line's MP3, made now if it isn't cached yet
"""

import hmac
from collections.abc import Callable
from typing import Annotated, Any, Literal

import anthropic
import httpx
from fastapi import BackgroundTasks, Depends, FastAPI, Header, HTTPException, Response
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field

from ailing import config, store
from ailing.ankimcp import ankimcp_call_tool
from ailing.engine import Engine, NotAvailable, NotFound
from ailing.generator import Ask, claude_ask
from ailing.lexicon import Entry
from ailing.reader import render
from ailing.store import Reading, Settings, StretchWords, Topic
from ailing.tts import AudioCache, azure_synthesize


class NewTopic(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    favorite: bool = True


class TopicUpdate(BaseModel):
    favorite: bool


class SettingsUpdate(BaseModel):
    stretch_words: StretchWords | None = None


class ReadingIn(BaseModel):
    rating: Literal["too_easy", "about_right", "too_hard"] | None = None
    finished: bool = False
    words_glossed: list[str] = []
    words_flagged: list[str] = []
    audio_speed: float | None = Field(default=None, ge=0.5, le=1.5)
    listen_only: bool = False
    seconds: int = Field(default=0, ge=0)


def create_app(engine: Engine, passphrase: str | None) -> FastAPI:
    app = FastAPI(title="ailing")

    def require_passphrase(authorization: Annotated[str | None, Header()] = None) -> None:
        if not passphrase:
            raise HTTPException(503, "The server has no passphrase set.")
        given = (authorization or "").removeprefix("Bearer ").strip()
        # Header values arrive decoded as latin-1, so turn them back into the bytes that were sent
        # before comparing with the passphrase's UTF-8 bytes; otherwise "pässword" never matches.
        if not hmac.compare_digest(given.encode("latin-1"), passphrase.encode()):
            raise HTTPException(401, "Wrong passphrase.")

    authed = [Depends(require_passphrase)]

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/api/check", status_code=204, dependencies=authed)
    async def check() -> Response:
        return Response(status_code=204)

    @app.get("/api/topics", dependencies=authed)
    async def topics(background: BackgroundTasks) -> list[dict[str, Any]]:
        background.add_task(engine.top_up)
        return [_topic(t, engine) for t in store.list_topics(engine.conn)]

    @app.post("/api/topics", dependencies=authed)
    async def add_topic(body: NewTopic, background: BackgroundTasks) -> dict[str, Any]:
        try:
            topic = store.add_topic(engine.conn, body.name, body.favorite, engine.clock())
        except ValueError as e:
            raise HTTPException(422, str(e)) from e
        background.add_task(engine.top_up)
        return _topic(topic, engine)

    @app.patch("/api/topics/{topic_id}", dependencies=authed)
    async def update_topic(topic_id: int, body: TopicUpdate) -> dict[str, Any]:
        topic = store.set_favorite(engine.conn, topic_id, body.favorite)
        if topic is None:
            raise HTTPException(404, "No such topic.")
        return _topic(topic, engine)

    @app.post("/api/topics/{topic_id}/next", dependencies=authed)
    async def next_text(topic_id: int, background: BackgroundTasks) -> Any:
        try:
            text = await engine.next_text(topic_id)
        except NotFound as e:
            raise HTTPException(404, "No such topic.") from e
        except NotAvailable as e:
            raise HTTPException(503, str(e)) from e
        if text is None:
            return JSONResponse({"writing": True}, status_code=202)
        background.add_task(engine.top_up)
        entries, lexicon = engine.snapshot()
        out = render(text, lexicon, {e.text: e.meaning for e in entries})
        speaks = engine.audio is not None and engine.synthesize is not None
        for i, line in enumerate(out["lines"]):
            line["audio"] = speaks or engine.has_audio(text.id, i)
        return out

    @app.get("/api/texts/{text_id}/lines/{line}/audio", dependencies=authed)
    async def line_audio(text_id: int, line: int) -> FileResponse:
        text = store.get_text(engine.conn, text_id)
        if text is None:
            raise HTTPException(404, "No such text.")
        path = await engine.line_audio(text, line)
        if path is None:
            raise HTTPException(404, "No audio for this line.")
        return FileResponse(path, media_type="audio/mpeg")

    @app.get("/api/settings", dependencies=authed)
    async def settings() -> dict[str, Any]:
        return store.load_settings(engine.conn).__dict__

    @app.patch("/api/settings", dependencies=authed)
    async def update_settings(body: SettingsUpdate) -> dict[str, Any]:
        current = store.load_settings(engine.conn)
        updated = Settings(stretch_words=body.stretch_words or current.stretch_words)
        store.save_settings(engine.conn, updated)
        return updated.__dict__

    @app.post("/api/texts/{text_id}/reading", status_code=204, dependencies=authed)
    async def reading(text_id: int, body: ReadingIn, background: BackgroundTasks) -> Response:
        try:
            engine.record_reading(
                text_id,
                Reading(
                    rating=body.rating,
                    finished=body.finished,
                    words_glossed=tuple(body.words_glossed),
                    words_flagged=tuple(body.words_flagged),
                    audio_speed=body.audio_speed,
                    listen_only=body.listen_only,
                    seconds=body.seconds,
                ),
            )
        except NotFound as e:
            raise HTTPException(404, "No such text.") from e
        background.add_task(engine.top_up)
        return Response(status_code=204)

    return app


def _topic(t: Topic, engine: Engine) -> dict[str, Any]:
    return {
        "id": t.id,
        "name": t.name,
        "favorite": t.favorite,
        "ready": t.ready,
        "state": engine.topic_state(t),
    }


def production_app() -> FastAPI:
    """Built on startup by `uvicorn --factory ailing.app:production_app`, so importing this module
    (as the tests do) opens no database and reads no secrets."""
    settings = config.load()
    settings.db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = store.connect(settings.db_path)
    ask_for: Callable[[list[Entry]], Ask] | None = None
    if key := settings.secrets.get("ANTHROPIC_API_KEY"):
        client = anthropic.AsyncAnthropic(api_key=key)

        def ask_for(entries: list[Entry]) -> Ask:
            return claude_ask(client, entries)

    synthesize = None
    key, region = (
        settings.secrets.get("AZURE_SPEECH_KEY"),
        settings.secrets.get("AZURE_SPEECH_REGION"),
    )
    if key and region:
        synthesize = azure_synthesize(key, region, httpx.AsyncClient())

    # Without ANKIMCP_URL the lexicon is never refreshed, and the server says it has no word list.
    anki_url = settings.secrets.get("ANKIMCP_URL")
    call_tool = (
        ankimcp_call_tool(anki_url, settings.secrets.get("ANKIMCP_TOKEN")) if anki_url else None
    )
    engine = Engine(
        conn,
        ask_for,
        call_tool=call_tool,
        synthesize=synthesize,
        audio=AudioCache(settings.audio_dir),
        voices=settings.voices,
    )
    return create_app(engine, settings.secrets.get("APP_PASSPHRASE"))
