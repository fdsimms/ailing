import type { ReaderText, Word } from "../api";
import { countOutsideDeck, isOutsideDeck, underFloor } from "../deckWords";

const word = (text: string, status: Word["status"]): Word => ({ text, status, gloss: null, stretch: false, deck: false });

test("unknown and partial words are outside the deck; known words and punctuation aren't", () => {
  expect(isOutsideDeck(word("ทอน", "unknown"))).toBe(true);
  expect(isOutsideDeck(word("รับ", "partial"))).toBe(true);
  expect(isOutsideDeck(word("ครับ", "known"))).toBe(false);
  expect(isOutsideDeck(word(" ", null))).toBe(false);
});

test("counts every occurrence across the lines", () => {
  const text: ReaderText = {
    id: 1,
    topicId: 1,
    title: "At the stall",
    coverage: 0.95,
    stretch: [],
    roles: {},
    form: "dialogue",
    language: "th",
    lines: [
      { speaker: "A", english: "", audio: false, words: [word("ทอน", "unknown"), word("ครับ", "known")] },
      { speaker: "B", english: "", audio: false, words: [word("ทอน", "unknown"), word("รับ", "partial")] },
    ],
  };
  expect(countOutsideDeck(text)).toBe(3);
});

test("a text under 95% is flagged as under the usual floor; one at 95% isn't", () => {
  const text = (coverage: number): ReaderText => ({
    id: 1,
    topicId: 1,
    title: "t",
    coverage,
    stretch: [],
    roles: {},
    form: "story",
    language: "th",
    lines: [],
  });
  expect(underFloor(text(0.923))).toBe(true);
  expect(underFloor(text(0.95))).toBe(false);
  expect(underFloor(text(1))).toBe(false);
});
