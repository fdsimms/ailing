// The progress card on the topics screen, in words. The goal is the Milestone 1 exit check
// (docs/brief.md): 10 or more texts in two weeks, median coverage 95% or higher, most ratings
// "about right".
import type { Progress } from "./api";

export const GOAL_TEXTS = 10;
const GOAL_COVERAGE = 0.95;

const percent = (ratio: number) => `${Math.round(ratio * 100)}%`;
const plural = (n: number, word: string) => `${n} ${word}${n === 1 ? "" : "s"}`;

export function goalMet(p: Progress): boolean {
  const rated = p.ratings.too_easy + p.ratings.about_right + p.ratings.too_hard;
  return (
    p.finished >= GOAL_TEXTS &&
    p.median_coverage !== null &&
    p.median_coverage >= GOAL_COVERAGE &&
    p.ratings.about_right * 2 > rated
  );
}

export function describeProgress(p: Progress): { headline: string; detail: string; next: string } {
  const headline = `${p.finished} of ${GOAL_TEXTS} texts finished in the last ${p.days} days`;
  const rated = p.ratings.too_easy + p.ratings.about_right + p.ratings.too_hard;
  let detail: string;
  if (p.finished === 0 || p.median_coverage === null) {
    detail = "Finish a text and rate it to see how it's going.";
  } else {
    const parts = [`Median ${percent(p.median_coverage)} known words.`];
    if (rated > 0) parts.push(`${p.ratings.about_right} of ${rated} rated about right.`);
    if (goalMet(p)) parts.push("Two-week goal met.");
    detail = parts.join(" ");
  }
  const next = `New texts aim for at least ${percent(p.next.floor)} known words and ${plural(
    p.next.stretch,
    "practice word",
  )}.`;
  return { headline, detail, next };
}
