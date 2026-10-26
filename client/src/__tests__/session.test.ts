import type { ReaderText } from "../api";
import { formatDuration, heard, isFlagged, lookUp, startSession, toggleFlag, toLog } from "../session";

const TEXT: ReaderText = { id: 7, topicId: 1, title: "t", coverage: 0.97, stretch: [], roles: {}, lines: [] };

test("looking a word up records it once", () => {
  let s = startSession(TEXT, 0);
  s = lookUp(lookUp(s, "ทอน"), "ทอน");
  s = lookUp(s, "กิน");
  expect(s.glossed).toEqual(["ทอน", "กิน"]);
});

test("marking a word unknown toggles", () => {
  let s = toggleFlag(startSession(TEXT, 0), "ทอน");
  expect(isFlagged(s, "ทอน")).toBe(true);
  s = toggleFlag(s, "ทอน");
  expect(isFlagged(s, "ทอน")).toBe(false);
});

test("the log carries the rating, the words and whole seconds", () => {
  let s = startSession(TEXT, 1_000);
  s = toggleFlag(lookUp(s, "ทอน"), "ทอน");
  expect(toLog(s, 96_400, "about_right", true)).toEqual({
    rating: "about_right",
    finished: true,
    words_glossed: ["ทอน"],
    words_flagged: ["ทอน"],
    audio_speed: null,
    listen_only: false,
    seconds: 95,
  });
});

test("a clock that went backwards logs zero seconds", () => {
  expect(toLog(startSession(TEXT, 5_000), 1_000, null, false).seconds).toBe(0);
});

test("durations read as minutes and seconds", () => {
  expect(formatDuration(0)).toBe("0:00");
  expect(formatDuration(134)).toBe("2:14");
});

test("the log carries the speed audio last played at", () => {
  const s = startSession(TEXT, 0);
  expect(toLog(s, 0, null, false).audio_speed).toBeNull();
  expect(toLog(heard(heard(s, 0.8), 0.9), 0, null, false).audio_speed).toBe(0.9);
});
