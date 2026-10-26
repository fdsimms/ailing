// The grammar row on the topics screen, in words.
import type { GrammarPoint } from "./api";

const plural = (n: number) => (n === 1 ? "point" : "points");

export function grammarSummary(points: GrammarPoint[]): string {
  const practicing = points.filter((p) => p.state === "practice").length;
  const avoiding = points.filter((p) => p.state === "avoid").length;
  const parts = [
    practicing > 0 ? `Practicing ${practicing} ${plural(practicing)}` : null,
    avoiding > 0 ? `${practicing > 0 ? "avoiding" : "Avoiding"} ${avoiding}` : null,
  ].filter(Boolean);
  return parts.length > 0 ? parts.join(", ") : "Nothing chosen";
}
