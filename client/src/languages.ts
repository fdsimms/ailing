// What the app says and shows differently per language. Thai counts only deck words as known;
// Spanish also counts the 10,000 most common words (docs/architecture.md, Languages).
import type { Language, Word } from "./api";

type LanguageInfo = {
  name: string;
  fontSize: number; // Thai sits bigger than Latin text at the same size
  lineHeight: number; // Thai needs room for marks above and below
  highlightLabel: string;
};

export const LANGUAGES: Record<Language, LanguageInfo> = {
  th: { name: "Thai", fontSize: 23, lineHeight: 1.75, highlightLabel: "Highlight words not in your deck" },
  es: { name: "Spanish", fontSize: 20, lineHeight: 1.5, highlightLabel: "Highlight words you might not know" },
};

export const LANGUAGE_ORDER: Language[] = ["th", "es"];

// For the gloss popover and the marked words list.
export function wordStatus(word: Pick<Word, "status" | "deck">): string {
  if (word.status === "partial") return "Only inside a longer phrase in your deck";
  if (word.status === "unknown") return "Not in your deck";
  return word.deck ? "In your deck" : "A common word";
}
