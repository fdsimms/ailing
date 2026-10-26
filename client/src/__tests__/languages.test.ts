import { wordStatus } from "../languages";

test("a word says whether it's a deck word, a common word, or neither", () => {
  expect(wordStatus({ status: "known", deck: true })).toBe("In your deck");
  expect(wordStatus({ status: "known", deck: false })).toBe("A common word");
  expect(wordStatus({ status: "partial", deck: false })).toBe("Only inside a longer phrase in your deck");
  expect(wordStatus({ status: "unknown", deck: false })).toBe("Not in your deck");
});
