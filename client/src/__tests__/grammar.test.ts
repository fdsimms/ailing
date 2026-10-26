import type { GrammarPoint } from "../api";
import { grammarSummary } from "../grammar";

const point = (id: string, state: GrammarPoint["state"]): GrammarPoint => ({ id, name: id, note: "", state });

test("the summary says how many points are practiced and avoided", () => {
  expect(grammarSummary([point("a", "normal")])).toBe("Nothing chosen");
  expect(grammarSummary([point("a", "practice")])).toBe("Practicing 1 point");
  expect(grammarSummary([point("a", "avoid"), point("b", "avoid")])).toBe("Avoiding 2");
  expect(grammarSummary([point("a", "practice"), point("b", "practice"), point("c", "avoid")])).toBe(
    "Practicing 2 points, avoiding 1",
  );
});
