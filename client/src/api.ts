// The server's API (server/src/ailing/app.py). Every call sends the passphrase; the server's own
// error sentences are passed through, since they're written to be shown as they are.

// "writing": a text is being written now. "failed": the last write failed and the server is
// waiting before it tries that topic again by itself.
export type TopicState = "ready" | "writing" | "failed" | "idle";

export type Topic = { id: number; name: string; favorite: boolean; ready: number; state: TopicState };

export type Word = {
  text: string;
  status: "known" | "partial" | "unknown" | null; // null for spaces and punctuation
  gloss: string | null;
  stretch: boolean;
  deck: boolean; // a deck word, as against one known for being common (Spanish)
};

// The languages texts are written in. Topics are shared; the rest is per language.
export type Language = "th" | "es";

// A and B are a dialogue's two speakers; N is a story's narrator.
export type TextLine = { speaker: "A" | "B" | "N"; english: string; words: Word[]; audio: boolean };

// A dialogue between two speakers, or a short story told by a narrator.
export type Form = "dialogue" | "story";

export type ReaderText = {
  id: number;
  topicId: number;
  title: string;
  coverage: number;
  stretch: string[];
  roles: Partial<Record<"A" | "B", string>>; // who each speaker is; empty for older texts and stories
  form: Form;
  language: Language;
  lines: TextLine[];
};

// "topic": the model picks stretch words that suit the topic from a list of due and newer words.
// "any": it's given words from that list at random and has to fit them in.
export type StretchWords = "topic" | "any";

// How many lines a dialogue has: short, medium or long.
export type Length = 6 | 8 | 12;

export type Settings = { stretch_words: StretchWords; lines: Length; form: Form; language: Language };

export type Rating = "too_easy" | "about_right" | "too_hard";

// Finished texts over the last `days` days (what the Milestone 1 exit check reads), and the
// difficulty new texts are written at.
export type Progress = {
  days: number;
  finished: number;
  median_coverage: number | null;
  ratings: Record<Rating | "none", number>;
  next: { floor: number; stretch: number };
};

// A topic idea not yet added. `fit` is the share of its key words the deck knows.
export type Suggestion = { name: string; fit: number };

// A text read to the end, to read or listen to again.
export type PastText = {
  id: number;
  topic: string;
  title: string;
  rating: Rating | null;
  read_at: string;
  coverage: number;
  form: Form;
};

// A word marked unknown in a reading and not cleared since.
export type MarkedWord = {
  word: string;
  gloss: string | null;
  status: "known" | "partial" | "unknown";
  deck: boolean;
  times: number;
  last_marked: string;
};

export type ReadingLog = {
  rating: Rating | null;
  finished: boolean;
  words_glossed: string[];
  words_flagged: string[];
  audio_speed: number | null;
  listen_only: boolean;
  seconds: number;
};

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message);
  }
}

type Fetch = (url: string, init: RequestInit) => Promise<Response>;

// `onUnauthorized` runs when the server rejects the passphrase (it was changed on the server), so
// the app can forget it and ask again instead of failing every call.
export function createApi(
  baseUrl: string,
  passphrase: string,
  fetchImpl: Fetch = fetch,
  onUnauthorized?: () => void,
) {
  const root = baseUrl.replace(/\/+$/, "");

  async function call<T>(method: string, path: string, body?: unknown): Promise<T> {
    let response: Response;
    try {
      response = await fetchImpl(root + path, {
        method,
        headers: {
          Authorization: `Bearer ${passphrase}`,
          ...(body === undefined ? {} : { "Content-Type": "application/json" }),
        },
        body: body === undefined ? undefined : JSON.stringify(body),
      });
    } catch {
      throw new ApiError("Couldn't reach the server. Check your connection and try again.", 0);
    }
    if (response.status === 401) onUnauthorized?.();
    if (!response.ok) throw new ApiError(await errorMessage(response), response.status);
    return response.status === 204 || response.status === 202
      ? (undefined as T)
      : ((await response.json()) as T);
  }

  return {
    check: () => call<void>("GET", "/api/check"),
    topics: () => call<Topic[]>("GET", "/api/topics"),
    addTopic: (name: string, favorite = true) => call<Topic>("POST", "/api/topics", { name, favorite }),
    suggestions: () => call<Suggestion[]>("GET", "/api/suggestions"),
    setFavorite: (id: number, favorite: boolean) =>
      call<Topic>("PATCH", `/api/topics/${id}`, { favorite }),
    removeTopic: (id: number) => call<void>("DELETE", `/api/topics/${id}`),
    progress: () => call<Progress>("GET", "/api/progress"),
    markedWords: () => call<MarkedWord[]>("GET", "/api/words"),
    clearWord: (word: string) => call<void>("POST", "/api/words/clear", { word }),
    settings: () => call<Settings>("GET", "/api/settings"),
    updateSettings: (settings: Partial<Settings>) => call<Settings>("PATCH", "/api/settings", settings),
    // null while the server is still writing the text (202): ask again in a few seconds.
    nextText: async (topicId: number) =>
      (await call<ReaderText | undefined>("POST", `/api/topics/${topicId}/next`)) ?? null,
    pastTexts: () => call<PastText[]>("GET", "/api/texts"),
    // A past text, to read again. Reading it again isn't logged.
    text: (textId: number) => call<ReaderText>("GET", `/api/texts/${textId}`),
    logReading: (textId: number, log: ReadingLog) =>
      call<void>("POST", `/api/texts/${textId}/reading`, log),
    // For the audio player, which fetches the file itself and so needs the passphrase too.
    audioSource: (textId: number, line: number) => ({
      uri: `${root}/api/texts/${textId}/lines/${line}/audio`,
      headers: { Authorization: `Bearer ${passphrase}` },
    }),
  };
}

export type Api = ReturnType<typeof createApi>;

export async function errorMessage(response: Response): Promise<string> {
  if (response.status === 401) return "That passphrase isn't right.";
  try {
    const body = (await response.json()) as { detail?: unknown };
    if (typeof body.detail === "string") return body.detail;
  } catch {
    // Not JSON; fall through to the generic message.
  }
  return `Something went wrong on the server (${response.status}). Try again.`;
}
