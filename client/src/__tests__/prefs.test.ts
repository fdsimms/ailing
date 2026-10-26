import { DEFAULT_PREFS, parsePrefs } from "../prefs";

test("saved settings come back", () => {
  expect(parsePrefs(JSON.stringify({ rate: 0.7, highlight: true }))).toEqual({ rate: 0.7, highlight: true });
});

test("nothing saved, or something unreadable, gives the defaults", () => {
  expect(parsePrefs(null)).toEqual(DEFAULT_PREFS);
  expect(parsePrefs("not json")).toEqual(DEFAULT_PREFS);
  expect(parsePrefs("null")).toEqual(DEFAULT_PREFS);
});

test("a speed the reader doesn't offer falls back on its own", () => {
  expect(parsePrefs(JSON.stringify({ rate: 2, highlight: true }))).toEqual({ rate: 0.9, highlight: true });
  expect(parsePrefs(JSON.stringify({ rate: 0.8, highlight: "yes" }))).toEqual({ rate: 0.8, highlight: false });
});
