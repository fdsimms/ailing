// Every word marked unknown while reading, newest first, with its meaning, so they can be looked at
// together and added to Anki by hand. Nothing here writes to Anki (CLAUDE.md, the approval rule).
// "Clear" takes a word off the list until it's marked again.
import { useCallback, useEffect, useState } from "react";
import { ActivityIndicator, RefreshControl, ScrollView, StyleSheet, Text, View } from "react-native";

import { type Api, ApiError, type MarkedWord } from "../api";
import { Card, ErrorNote, Hint, NavBar, PillButton } from "../components/ui";
import { font, spacing, thaiFont, useColors } from "../theme";

const STATUS: Record<MarkedWord["status"], string> = {
  known: "In your deck",
  partial: "Only inside a longer phrase in your deck",
  unknown: "Not in your deck",
};

export function WordsScreen({ api, onBack }: { api: Api; onBack: () => void }) {
  const c = useColors();
  const [words, setWords] = useState<MarkedWord[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [refreshing, setRefreshing] = useState(false);

  const load = useCallback(async () => {
    try {
      setWords(await api.markedWords());
      setError(null);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Couldn't load your marked words.");
    }
  }, [api]);

  useEffect(() => {
    load();
  }, [load]);

  async function clear(word: string) {
    const before = words;
    setWords((ws) => ws?.filter((w) => w.word !== word) ?? ws);
    try {
      await api.clearWord(word);
    } catch (e) {
      setWords(before);
      setError(e instanceof ApiError ? e.message : "Couldn't clear that word. Try again.");
    }
  }

  return (
    <View style={styles.root}>
      <NavBar back="Topics" title="Marked words" onBack={onBack} />
      <ScrollView
        contentContainerStyle={styles.content}
        refreshControl={
          <RefreshControl
            refreshing={refreshing}
            onRefresh={async () => {
              setRefreshing(true);
              await load();
              setRefreshing(false);
            }}
          />
        }
      >
        {error ? <ErrorNote message={error} onRetry={load} /> : null}
        {words === null && !error ? <ActivityIndicator style={styles.loading} /> : null}
        {words !== null && words.length === 0 ? (
          <Text style={[styles.empty, { color: c.textSecondary }]}>
            No marked words. While reading, tap a word and choose Mark as unknown.
          </Text>
        ) : null}
        {words !== null && words.length > 0 ? (
          <>
            <Card>
              {words.map((w, i) => (
                <View
                  key={w.word}
                  style={[styles.row, i > 0 && { borderTopWidth: StyleSheet.hairlineWidth, borderTopColor: c.separator }]}
                >
                  <View style={styles.rowText}>
                    <Text style={[styles.word, { color: c.text }]}>{w.word}</Text>
                    <Text style={[styles.gloss, { color: c.text }]}>{w.gloss ?? "No meaning available"}</Text>
                    <Text style={[styles.meta, { color: c.textTertiary }]}>
                      {STATUS[w.status]}
                      {w.times > 1 ? `. Marked ${w.times} times.` : ""}
                    </Text>
                  </View>
                  <PillButton label="Clear" quiet onPress={() => clear(w.word)} />
                </View>
              ))}
            </Card>
            <Hint>Only saved here. Nothing is added to Anki. Clear a word once you've dealt with it.</Hint>
          </>
        ) : null}
      </ScrollView>
    </View>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1 },
  content: { paddingTop: spacing.sm, paddingBottom: spacing.xl },
  loading: { marginTop: spacing.xl },
  empty: { fontSize: font.md, lineHeight: 21, textAlign: "center", padding: spacing.lg },
  row: { flexDirection: "row", alignItems: "center", gap: spacing.smd, padding: spacing.md },
  rowText: { flex: 1 },
  word: { fontSize: thaiFont, lineHeight: thaiFont * 1.5 },
  gloss: { fontSize: font.md },
  meta: { fontSize: font.sm, marginTop: 2 },
});
