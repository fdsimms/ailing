import type { Progress } from "../api";
import { describeProgress, goalMet } from "../progress";

const base: Progress = {
  days: 14,
  finished: 0,
  median_coverage: null,
  ratings: { too_easy: 0, about_right: 0, too_hard: 0, none: 0 },
  next: { floor: 0.95, stretch: 2 },
};

test("with nothing finished it says what to do", () => {
  expect(describeProgress(base)).toEqual({
    headline: "0 of 10 texts finished in the last 14 days",
    detail: "Finish a text and rate it to see how it's going.",
    next: "New texts aim for at least 95% known words and 2 practice words.",
  });
});

test("it reports coverage and ratings, and says when the goal is met", () => {
  const p: Progress = {
    ...base,
    finished: 11,
    median_coverage: 0.967,
    ratings: { too_easy: 2, about_right: 7, too_hard: 1, none: 1 },
    next: { floor: 0.97, stretch: 1 },
  };
  expect(goalMet(p)).toBe(true);
  expect(describeProgress(p).detail).toBe("Median 97% known words. 7 of 10 rated about right. Two-week goal met.");
  expect(describeProgress(p).next).toBe("New texts aim for at least 97% known words and 1 practice word.");
});

test("the goal needs most rated texts to be about right", () => {
  const p: Progress = {
    ...base,
    finished: 12,
    median_coverage: 0.98,
    ratings: { too_easy: 3, about_right: 6, too_hard: 3, none: 0 },
  };
  expect(goalMet(p)).toBe(false);
  expect(goalMet({ ...p, median_coverage: 0.94, ratings: { ...p.ratings, about_right: 10 } })).toBe(false);
});
