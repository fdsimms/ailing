// The server's API (server/src/ailing/app.py). Every call sends the passphrase; the server's own
// error sentences are passed through, since they're written to be shown as they are.

export type Topic = { id: number; name: string; favorite: boolean; ready: number };

export type Word = {
  text: string;
  status: "known" | "partial" | "unknown" | null; // null for spaces and punctuation
  gloss: string | null;
  stretch: boolean;
};

export type TextLine = { speaker: "A" | "B"; english: string; words: Word[] };

export type ReaderText = {
  id: number;
  topicId: number;
  title: string;
  coverage: number;
  stretch: string[];
  lines: TextLine[];
};

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

export function createApi(baseUrl: string, passphrase: string, fetchImpl: Fetch = fetch) {
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
    if (!response.ok) throw new ApiError(await errorMessage(response), response.status);
    return response.status === 204 ? (undefined as T) : ((await response.json()) as T);
  }

  return {
    check: () => call<void>("GET", "/api/check"),
    topics: () => call<Topic[]>("GET", "/api/topics"),
    addTopic: (name: string) => call<Topic>("POST", "/api/topics", { name, favorite: true }),
    setFavorite: (id: number, favorite: boolean) =>
      call<Topic>("PATCH", `/api/topics/${id}`, { favorite }),
    nextText: (topicId: number) => call<ReaderText>("POST", `/api/topics/${topicId}/next`),
    logReading: (textId: number, log: ReadingLog) =>
      call<void>("POST", `/api/texts/${textId}/reading`, log),
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
