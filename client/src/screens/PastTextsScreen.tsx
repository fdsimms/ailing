// Texts read to the end, newest first. Opening one reads it again in the reader, with nothing
// logged (docs/architecture.md, Client).
import { useCallback, useEffect, useState } from "react";
import { ActivityIndicator, Pressable, RefreshControl, ScrollView, StyleSheet, Text, View } from "react-native";

import { type Api, ApiError, type PastText, type Rating } from "../api";
import { Card, ErrorNote, Hint, NavBar } from "../components/ui";
import { font, spacing, useColors } from "../theme";

const RATING_TEXT: Record<Rating, string> = {
  too_easy: "Too easy",
  about_right: "About right",
  too_hard: "Too hard",
};

// "Oct 26", from the server's ISO timestamp.
function shortDate(iso: string): string {
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? "" : d.toLocaleDateString("en-US", { month: "short", day: "numeric" });
}

export function PastTextsScreen({
  api,
  onOpen,
  onBack,
}: {
  api: Api;
  onOpen: (text: PastText) => void;
  onBack: () => void;
}) {
  const c = useColors();
  const [texts, setTexts] = useState<PastText[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [refreshing, setRefreshing] = useState(false);

  const load = useCallback(async () => {
    try {
      setTexts(await api.pastTexts());
      setError(null);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Couldn't load your past texts.");
    }
  }, [api]);

  useEffect(() => {
    load();
  }, [load]);

  return (
    <View style={styles.root}>
      <NavBar back="Topics" title="Past texts" onBack={onBack} />
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
        {texts === null && !error ? <ActivityIndicator style={styles.loading} /> : null}
        {texts !== null && texts.length === 0 ? (
          <Text style={[styles.empty, { color: c.textSecondary }]}>
            No past texts yet. Texts you finish show up here, to read or listen to again.
          </Text>
        ) : null}
        {texts !== null && texts.length > 0 ? (
          <>
            <Card>
              {texts.map((t, i) => {
                const meta = [
                  t.topic,
                  t.form === "story" ? "Story" : null,
                  shortDate(t.read_at),
                  t.rating ? RATING_TEXT[t.rating] : null,
                ]
                  .filter(Boolean)
                  .join(" · ");
                return (
                  <Pressable
                    key={t.id}
                    onPress={() => onOpen(t)}
                    accessibilityRole="button"
                    accessibilityLabel={`${t.title}, ${meta}`}
                    accessibilityHint="Opens this text again"
                    style={({ pressed }) => [
                      styles.row,
                      i > 0 && { borderTopWidth: StyleSheet.hairlineWidth, borderTopColor: c.separator },
                      { opacity: pressed ? 0.7 : 1 },
                    ]}
                  >
                    <View style={styles.rowText}>
                      <Text style={[styles.title, { color: c.text }]}>{t.title}</Text>
                      <Text style={[styles.meta, { color: c.textSecondary }]}>{meta}</Text>
                    </View>
                    <Text style={[styles.chevron, { color: c.textTertiary }]}>›</Text>
                  </Pressable>
                );
              })}
            </Card>
            <Hint>Reading a text again isn't logged and doesn't change how hard new texts are.</Hint>
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
  row: { flexDirection: "row", alignItems: "center", gap: spacing.sm, padding: spacing.md },
  rowText: { flex: 1, gap: 2 },
  title: { fontSize: font.lg },
  meta: { fontSize: font.sm },
  chevron: { fontSize: font.xl },
});
