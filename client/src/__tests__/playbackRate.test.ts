import { clampRate, MAX_RATE, MIN_RATE } from "../playbackRate";

test("keeps a rate inside 0.7 to 1.0", () => {
  expect(clampRate(0.5)).toBe(MIN_RATE);
  expect(clampRate(1.5)).toBe(MAX_RATE);
  expect(clampRate(0.8)).toBe(0.8);
});

test("snaps to tenths", () => {
  expect(clampRate(0.84)).toBe(0.8);
  expect(clampRate(0.86)).toBe(0.9);
});

test("falls back to normal speed for a bad value", () => {
  expect(clampRate(Number.NaN)).toBe(MAX_RATE);
});
