import { ApiError, createApi } from "../api";

type Call = { url: string; init: RequestInit };

function fakeFetch(response: Response | Error) {
  const calls: Call[] = [];
  const impl = async (url: string, init: RequestInit) => {
    calls.push({ url, init });
    if (response instanceof Error) throw response;
    return response;
  };
  return { impl, calls };
}

const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });

test("sends the passphrase and the body to the right route", async () => {
  const { impl, calls } = fakeFetch(json({ id: 1, name: "Taxi", favorite: true, ready: 0 }));
  const api = createApi("https://ailing.fly.dev/", "open sesame", impl);

  const topic = await api.addTopic("Taxi");

  expect(topic.name).toBe("Taxi");
  expect(calls[0].url).toBe("https://ailing.fly.dev/api/topics");
  expect(calls[0].init.method).toBe("POST");
  expect((calls[0].init.headers as Record<string, string>).Authorization).toBe("Bearer open sesame");
  expect(JSON.parse(calls[0].init.body as string)).toEqual({ name: "Taxi", favorite: true });
});

test("a 204 resolves with nothing", async () => {
  const { impl } = fakeFetch(new Response(null, { status: 204 }));
  await expect(createApi("https://x", "p", impl).check()).resolves.toBeUndefined();
});

test("the server's own sentence becomes the error message", async () => {
  const { impl } = fakeFetch(json({ detail: "The server has no Claude API key yet." }, 503));
  const error = await createApi("https://x", "p", impl).nextText(1).catch((e) => e);
  expect(error).toBeInstanceOf(ApiError);
  expect(error.message).toBe("The server has no Claude API key yet.");
  expect(error.status).toBe(503);
});

test("a wrong passphrase says so", async () => {
  const { impl } = fakeFetch(json({ detail: "Wrong passphrase." }, 401));
  await expect(createApi("https://x", "p", impl).check()).rejects.toThrow("That passphrase isn't right.");
});

test("a non-JSON error and a network failure still read plainly", async () => {
  const html = fakeFetch(new Response("<html>", { status: 502 }));
  await expect(createApi("https://x", "p", html.impl).topics()).rejects.toThrow(
    "Something went wrong on the server (502). Try again.",
  );
  const offline = fakeFetch(new TypeError("Network request failed"));
  await expect(createApi("https://x", "p", offline.impl).topics()).rejects.toThrow(
    "Couldn't reach the server. Check your connection and try again.",
  );
});

test("a text still being written comes back as null", async () => {
  const { impl } = fakeFetch(json({ writing: true }, 202));
  await expect(createApi("https://x", "p", impl).nextText(1)).resolves.toBeNull();
});

test("a rejected passphrase tells the app, so it can ask again", async () => {
  const { impl } = fakeFetch(json({ detail: "Wrong passphrase." }, 401));
  const onUnauthorized = jest.fn();
  await createApi("https://x", "p", impl, onUnauthorized).topics().catch(() => {});
  expect(onUnauthorized).toHaveBeenCalledTimes(1);
});

test("other errors don't log the app out", async () => {
  const { impl } = fakeFetch(json({ detail: "The server has no Claude API key yet." }, 503));
  const onUnauthorized = jest.fn();
  await createApi("https://x", "p", impl, onUnauthorized).nextText(1).catch(() => {});
  expect(onUnauthorized).not.toHaveBeenCalled();
});

test("changing a setting sends only that field", async () => {
  const { impl, calls } = fakeFetch(json({ stretch_words: "any" }));
  const settings = await createApi("https://x", "p", impl).updateSettings({ stretch_words: "any" });
  expect(settings.stretch_words).toBe("any");
  expect(calls[0].url).toBe("https://x/api/settings");
  expect(calls[0].init.method).toBe("PATCH");
  expect(JSON.parse(calls[0].init.body as string)).toEqual({ stretch_words: "any" });
});
