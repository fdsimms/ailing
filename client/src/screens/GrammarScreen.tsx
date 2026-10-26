// The current language's grammar points, each practiced (used at least twice in every text),
// avoided (kept out) or normal. The server checks each text for them and sends back a draft that
// misses (docs/architecture.md, Grammar).
import { useCallback, useEffect, useState } from "react";
import { ActivityIndicator, ScrollView, StyleSheet, Text, View } from "react-native";

import { type Api, ApiError, type GrammarPoint, type GrammarState } from "../api";
import { Card, ErrorNote, Hint, NavBar, Segments } from "../components/ui";
import { font, spacing, useColors } from "../theme";

const STATES: { value: GrammarState; label: string }[] = [
  { value: "practice", label: "Practice" },
  { value: "normal", label: "Normal" },
  { value: "avoid", label: "Avoid" },
];

export function GrammarScreen({ api, onBack }: { api: Api; onBack: () => void }) {
  const c = useColors();
  const [points, setPoints] = useState<GrammarPoint[] | null>(null);
  const [maxPractice, setMaxPractice] = useState(2);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const body = await api.grammar();
      setPoints(body.points);
      setMaxPractice(body.max_practice);
      setError(null);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Couldn't load the grammar list.");
    }
  }, [api]);

  useEffect(() => {
    load();
  }, [load]);

  async function choose(id: string, state: GrammarState) {
    const before = points;
    setPoints((ps) => ps?.map((p) => (p.id === id ? { ...p, state } : p)) ?? ps);
    setError(null);
    try {
      setPoints((await api.setGrammar(id, state)).points);
    } catch (e) {
      setPoints(before);
      setError(e instanceof ApiError ? e.message : "Couldn't change that. Try again.");
    }
  }

  return (
    <View style={styles.root}>
      <NavBar back="Topics" title="Grammar" onBack={onBack} />
      <ScrollView contentContainerStyle={styles.content}>
        <Hint>
          {`Practice: used at least twice in every text, at most ${maxPractice} at a time. Avoid: left out, for grammar you haven't learned yet. Applies from the next text written.`}
        </Hint>
        {error ? <ErrorNote message={error} /> : null}
        {points === null && !error ? <ActivityIndicator style={styles.loading} /> : null}
        {points && points.length > 0 ? (
          <View style={styles.list}>
            <Card>
              {points.map((p, i) => (
                <View
                  key={p.id}
                  style={[styles.row, i > 0 && { borderTopWidth: StyleSheet.hairlineWidth, borderTopColor: c.separator }]}
                >
                  <Text style={[styles.name, { color: c.text }]}>{p.name}</Text>
                  <Text style={[styles.note, { color: c.textSecondary }]}>{p.note}</Text>
                  <Segments<GrammarState>
                    style={styles.states}
                    options={STATES.map((s) => ({ ...s, accessibilityLabel: `${s.label} ${p.name}` }))}
                    value={p.state}
                    onChange={(state) => choose(p.id, state)}
                  />
                </View>
              ))}
            </Card>
          </View>
        ) : null}
        <Hint>The server checks each text for these and rewrites one that misses, so most texts follow them.</Hint>
      </ScrollView>
    </View>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1 },
  content: { paddingTop: spacing.sm, paddingBottom: spacing.xl },
  loading: { marginTop: spacing.xl },
  list: { marginTop: spacing.md },
  row: { padding: spacing.md, gap: spacing.xs },
  name: { fontSize: font.lg, fontWeight: "600" },
  note: { fontSize: font.md },
  states: { marginTop: spacing.sm },
});
