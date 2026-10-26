// Which words in a text aren't in the deck: ones the deck doesn't hold at all, and ones it holds
// only inside a longer card (รับ inside รับอะไรดี). Coverage counts both as unknown, so the reader's
// highlight marks exactly the words the text was scored against.
import type { ReaderText, Word } from "./api";

export function isOutsideDeck(word: Word): boolean {
  return word.status === "unknown" || word.status === "partial";
}

export function countOutsideDeck(text: ReaderText): number {
  return text.lines.reduce((n, line) => n + line.words.filter(isOutsideDeck).length, 0);
}

// The usual floor. A text under it is the closest of the server's attempts, kept because it's still
// at 90% or more (docs/architecture.md, Generation and coverage), so the reader says so.
export const FLOOR = 0.95;

export function underFloor(text: ReaderText): boolean {
  return text.coverage < FLOOR;
}
