"""The HTTP API the iOS app calls. Every /api route needs the passphrase as a bearer token
(docs/architecture.md, Hosting); /health doesn't, so Fly can check the machine.

    GET   /api/check                  204 if the passphrase is right
    GET   /api/topics                 topics with their state and ready count; tops up in the background
    POST  /api/topics                 {name, favorite?} adds a topic (or returns the existing one)
    PATCH /api/topics/{id}            {favorite}
    DELETE /api/topics/{id}           removes a topic from the list (adding it again brings it back)
    GET   /api/suggestions            topic ideas not yet added, the best fit for the deck first
    POST  /api/topics/{id}/next       the next text for a topic; 202 {"writing": true} while one is
                                      being written in the background, so ask again shortly
    GET   /api/settings               {stretch_words: "topic" | "any", lines: 6 | 8 | 12,
                                      form: "dialogue" | "story", language: "th" | "es"}

Topics are shared by both languages. Everything else (ready texts, /next, progress, past texts,
marked words, ideas) is in the current language, the `language` setting.
    PATCH /api/settings               the same fields; takes effect from the next text written
    GET   /api/texts                  texts read to the end, newest first, to read again
    GET   /api/texts/{id}             one text, in the same shape as /next; reading it again isn't logged
    POST  /api/texts/{id}/reading     logs a session with a text and adjusts difficulty
    GET   /api/progress               finished texts, coverage and ratings over the last 14 days,
                                      and the difficulty the next text is written at
    GET   /api/words                  words marked unknown and not cleared, newest first
    POST  /api/words/clear            {word} takes a word off that list until it's marked again
    GET   /api/texts/{id}/lines/{n}/audio   one line's MP3, made now if it isn't cached yet
"""

import hmac
from collections.abc import Callable
from datetime import timedelta
from typing import Annotated, Any, Literal

import anthropic
import httpx
from fastapi import BackgroundTasks, Depends, FastAPI, Header, HTTPException, Response
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field

from ailing import config, store
from ailing.ankimcp import ankimcp_call_tool
from ailing.engine import Engine, NotAvailable, NotFound
from ailing.generator import Ask, Form, claude_ask
from ailing.languages import Code
from ailing.lexicon import Entry
from ailing.reader import gloss_for, render
from ailing.store import Length, Reading, Settings, StoredText, StretchWords, Topic
from ailing.suggestions import suggest
from ailing.tts import AudioCache, azure_synthesize

# The window the progress summary covers: the Milestone 1 exit check's two weeks.
PROGRESS_DAYS = 14
# How many past texts the list shows.
PAST_TEXTS = 50


class NewTopic(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    favorite: bool = True


class TopicUpdate(BaseModel):
    favorite: bool


class ClearWord(BaseModel):
    word: str = Field(min_length=1, max_length=100)


class SettingsUpdate(BaseModel):
    stretch_words: StretchWords | None = None
    lines: Length | None = None
    form: Form | None = None
    language: Code | None = None


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
        language = engine.language()
        return [_topic(t, engine, language) for t in store.list_topics(engine.conn, language)]

    @app.post("/api/topics", dependencies=authed)
    async def add_topic(body: NewTopic, background: BackgroundTasks) -> dict[str, Any]:
        try:
            topic = store.add_topic(engine.conn, body.name, body.favorite, engine.clock())
        except ValueError as e:
            raise HTTPException(422, str(e)) from e
        background.add_task(engine.top_up)
        return _topic(topic, engine, engine.language())

    @app.patch("/api/topics/{topic_id}", dependencies=authed)
    async def update_topic(topic_id: int, body: TopicUpdate) -> dict[str, Any]:
        topic = store.set_favorite(engine.conn, topic_id, body.favorite)
        if topic is None:
            raise HTTPException(404, "No such topic.")
        return _topic(topic, engine, engine.language())

    @app.delete("/api/topics/{topic_id}", status_code=204, dependencies=authed)
    async def remove_topic(topic_id: int) -> Response:
        if not store.remove_topic(engine.conn, topic_id):
            raise HTTPException(404, "No such topic.")
        return Response(status_code=204)

    @app.get("/api/suggestions", dependencies=authed)
    async def suggestions() -> list[dict[str, Any]]:
        language = engine.language()
        _, lexicon = engine.snapshot(language)
        taken = store.topic_names(engine.conn)
        return [{"name": s.name, "fit": s.fit} for s in suggest(lexicon, taken, language)]

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
        return _rendered(text, engine)

    @app.get("/api/texts", dependencies=authed)
    async def past_texts() -> list[dict[str, Any]]:
        return [
            {
                "id": t.id,
                "topic": t.topic,
                "title": t.title,
                "rating": t.rating,
                "read_at": t.read_at.isoformat(),
                "coverage": t.coverage,
                "form": t.form,
            }
            for t in store.past_texts(engine.conn, PAST_TEXTS, engine.language())
        ]

    @app.get("/api/texts/{text_id}", dependencies=authed)
    async def get_text(text_id: int) -> dict[str, Any]:
        text = store.get_text(engine.conn, text_id)
        if text is None or store.text_status(engine.conn, text_id) == "dropped":
            raise HTTPException(404, "No such text.")
        return _rendered(text, engine)

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
        updated = Settings(
            stretch_words=body.stretch_words or current.stretch_words,
            lines=body.lines or current.lines,
            form=body.form or current.form,
            language=body.language or current.language,
        )
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

    @app.get("/api/progress", dependencies=authed)
    async def progress() -> dict[str, Any]:
        language = engine.language()
        since = engine.clock() - timedelta(days=PROGRESS_DAYS)
        done = store.progress(engine.conn, since, language)
        difficulty = store.load_difficulty(engine.conn, language)
        return {
            "days": PROGRESS_DAYS,
            "finished": done.finished,
            "median_coverage": done.median_coverage,
            "ratings": done.ratings,
            "next": {"floor": difficulty.floor, "stretch": difficulty.stretch},
        }

    @app.get("/api/words", dependencies=authed)
    async def words() -> list[dict[str, Any]]:
        language = engine.language()
        entries, lexicon = engine.snapshot(language)
        meanings = {e.text: e.meaning for e in entries}
        return [
            {
                "word": w.word,
                "gloss": gloss_for(w.word, w.glosses, lexicon, meanings),
                "status": lexicon.status(w.word),
                "times": w.times,
                "last_marked": w.last_marked.isoformat(),
            }
            for w in store.marked_words(engine.conn, language)
        ]

    @app.post("/api/words/clear", status_code=204, dependencies=authed)
    async def clear_word(body: ClearWord) -> Response:
        store.clear_word(engine.conn, body.word, engine.clock())
        return Response(status_code=204)

    return app


def _rendered(text: StoredText, engine: Engine) -> dict[str, Any]:
    entries, lexicon = engine.snapshot(text.language)
    out = render(text, lexicon, {e.text: e.meaning for e in entries})
    speaks = engine.audio is not None and engine.synthesize is not None
    for i, line in enumerate(out["lines"]):
        line["audio"] = speaks or engine.has_audio(text.id, i)
    return out


def _topic(t: Topic, engine: Engine, language: Code) -> dict[str, Any]:
    # A topic's ready count is per language, so it's read again for the one being shown.
    t = store.get_topic(engine.conn, t.id, language) or t
    return {
        "id": t.id,
        "name": t.name,
        "favorite": t.favorite,
        "ready": t.ready,
        "state": engine.topic_state(t, language),
    }


def production_app() -> FastAPI:
    """Built on startup by `uvicorn --factory ailing.app:production_app`, so importing this module
    (as the tests do) opens no database and reads no secrets."""
    settings = config.load()
    settings.db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = store.connect(settings.db_path)
    ask_for: Callable[[list[Entry], Code], Ask] | None = None
    if key := settings.secrets.get("ANTHROPIC_API_KEY"):
        client = anthropic.AsyncAnthropic(api_key=key)

        def ask_for(entries: list[Entry], language: Code) -> Ask:
            return claude_ask(client, entries, language)

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
