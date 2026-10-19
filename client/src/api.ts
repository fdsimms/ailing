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
};

export type TextLine = { speaker: "A" | "B"; english: string; words: Word[]; audio: boolean };

export type ReaderText = {
  id: number;
  topicId: number;
  title: string;
  coverage: number;
  stretch: string[];
  lines: TextLine[];
};

// "topic": the model picks stretch words that suit the topic from a list of due and newer words.
// "any": it's given words from that list at random and has to fit them in.
export type StretchWords = "topic" | "any";

export type Settings = { stretch_words: StretchWords };

export type Rating = "too_easy" | "about_right" | "too_hard";

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
    addTopic: (name: string) => call<Topic>("POST", "/api/topics", { name, favorite: true }),
    setFavorite: (id: number, favorite: boolean) =>
      call<Topic>("PATCH", `/api/topics/${id}`, { favorite }),
    settings: () => call<Settings>("GET", "/api/settings"),
    updateSettings: (settings: Partial<Settings>) => call<Settings>("PATCH", "/api/settings", settings),
    // null while the server is still writing the text (202): ask again in a few seconds.
    nextText: async (topicId: number) =>
      (await call<ReaderText | undefined>("POST", `/api/topics/${topicId}/next`)) ?? null,
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
