import { firstLine, nextLine } from "../playback";

const lines = [{ audio: false }, { audio: true }, { audio: false }, { audio: true }];

test("play starts at the first line that has audio", () => {
  expect(firstLine(lines)).toBe(1);
  expect(firstLine([{ audio: false }])).toBeNull();
});

test("playing the dialogue moves on, skipping silent lines, and stops at the end", () => {
  expect(nextLine(lines, 1, true)).toBe(3);
  expect(nextLine(lines, 3, true)).toBeNull();
});

test("a replayed line plays alone", () => {
  expect(nextLine(lines, 1, false)).toBeNull();
});
