import { scrollTarget } from "../follow";

test("a line already in view needs no scroll", () => {
  expect(scrollTarget({ y: 300, height: 80 }, 200, 500)).toBeNull();
});

test("a line below the view scrolls up to just above it", () => {
  expect(scrollTarget({ y: 900, height: 80 }, 200, 500)).toBe(884);
});

test("a line above the view, or cut off at the bottom, scrolls too", () => {
  expect(scrollTarget({ y: 100, height: 80 }, 200, 500)).toBe(84);
  expect(scrollTarget({ y: 650, height: 80 }, 200, 500)).toBe(634);
});

test("never scrolls past the top", () => {
  expect(scrollTarget({ y: 4, height: 80 }, 50, 500)).toBe(0);
});
