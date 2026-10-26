import { ideaPage } from "../ideas";

const ideas = ["a", "b", "c", "d", "e"];

test("shows a few at a time and wraps back to the start", () => {
  expect(ideaPage(ideas, 0, 2)).toEqual(["a", "b"]);
  expect(ideaPage(ideas, 2, 2)).toEqual(["e"]);
  expect(ideaPage(ideas, 3, 2)).toEqual(["a", "b"]);
});

test("no ideas shows none", () => {
  expect(ideaPage([], 4)).toEqual([]);
});
