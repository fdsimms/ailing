// The reader's settings that last between launches: playback speed and whether words outside the
// deck are highlighted. Pure, so it's tested; savedPrefs.ts keeps them in the keychain.
import { RATES } from "./playbackRate";

export type Prefs = { rate: number; highlight: boolean };

export const DEFAULT_PREFS: Prefs = { rate: 0.9, highlight: false };

// Anything unreadable or out of range falls back to the default for that setting.
export function parsePrefs(raw: string | null): Prefs {
  let saved: Partial<Record<keyof Prefs, unknown>> = {};
  try {
    const parsed: unknown = raw ? JSON.parse(raw) : {};
    if (parsed && typeof parsed === "object") saved = parsed as typeof saved;
  } catch {
    // Not JSON: use the defaults.
  }
  return {
    rate: typeof saved.rate === "number" && RATES.includes(saved.rate) ? saved.rate : DEFAULT_PREFS.rate,
    highlight: typeof saved.highlight === "boolean" ? saved.highlight : DEFAULT_PREFS.highlight,
  };
}
