// One reading of one text: what was looked up, what was marked unknown, and how long it took.
// Pure, so it's tested; the reader screen holds one of these in state.
import type { Rating, ReaderText, ReadingLog } from "./api";

export type Session = {
  textId: number;
  startedAt: number;
  glossed: string[];
  flagged: string[];
};

export function startSession(text: ReaderText, now: number): Session {
  return { textId: text.id, startedAt: now, glossed: [], flagged: [] };
}

export function lookUp(session: Session, word: string): Session {
  return session.glossed.includes(word) ? session : { ...session, glossed: [...session.glossed, word] };
}

export function toggleFlag(session: Session, word: string): Session {
  const flagged = session.flagged.includes(word)
    ? session.flagged.filter((w) => w !== word)
    : [...session.flagged, word];
  return { ...session, flagged };
}

export function isFlagged(session: Session, word: string): boolean {
  return session.flagged.includes(word);
}

export function toLog(
  session: Session,
  now: number,
  rating: Rating | null,
  finished: boolean,
): ReadingLog {
  return {
    rating,
    finished,
    words_glossed: session.glossed,
    words_flagged: session.flagged,
    audio_speed: null, // set once the reader plays audio
    listen_only: false,
    seconds: Math.max(0, Math.round((now - session.startedAt) / 1000)),
  };
}

export function formatDuration(seconds: number): string {
  const m = Math.floor(seconds / 60);
  const s = seconds % 60;
  return `${m}:${String(s).padStart(2, "0")}`;
}
