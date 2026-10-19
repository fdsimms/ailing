import { useCallback, useEffect, useState } from "react";
import {
  ActivityIndicator,
  Pressable,
  RefreshControl,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  View,
} from "react-native";

import { type Api, ApiError, type Topic } from "../api";
import { Card, ErrorNote, Hint, PillButton, SectionLabel } from "../components/ui";
import { font, radius, spacing, useColors } from "../theme";

// While a favorite is still being written, check back this often.
const WRITING_POLL_MS = 10_000;

export function TopicsScreen({ api, onOpen }: { api: Api; onOpen: (topic: Topic) => void }) {
  const c = useColors();
  const [topics, setTopics] = useState<Topic[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [refreshing, setRefreshing] = useState(false);
  const [newName, setNewName] = useState("");

  const load = useCallback(async () => {
    try {
      setTopics(await api.topics());
      setError(null);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Couldn't load your topics.");
    }
  }, [api]);

  useEffect(() => {
    load();
  }, [load]);

  const writing = topics?.some((t) => t.favorite && t.ready === 0) ?? false;
  useEffect(() => {
    if (!writing) return;
    const id = setInterval(load, WRITING_POLL_MS);
    return () => clearInterval(id);
  }, [writing, load]);

  async function add() {
    const name = newName.trim();
    if (!name) return;
    try {
      await api.addTopic(name);
      setNewName("");
      await load();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Couldn't add that topic.");
    }
  }

  async function toggleFavorite(topic: Topic) {
    try {
      await api.setFavorite(topic.id, !topic.favorite);
      await load();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Couldn't change that topic.");
    }
  }

  const favorites = topics?.filter((t) => t.favorite) ?? [];
  const others = topics?.filter((t) => !t.favorite) ?? [];

  return (
    <ScrollView
      contentContainerStyle={styles.content}
      keyboardShouldPersistTaps="handled"
      automaticallyAdjustKeyboardInsets
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
      <Text style={[styles.title, { color: c.text }]}>Read &amp; Listen</Text>
      <Text style={[styles.sub, { color: c.textSecondary }]}>
        Pick a topic. Texts use words from your Thai deck.
      </Text>

      {error ? <ErrorNote message={error} onRetry={load} /> : null}
      {topics === null && !error ? <ActivityIndicator style={styles.loading} /> : null}

      {favorites.length > 0 ? (
        <>
          <SectionLabel>Favorites</SectionLabel>
          <Card>
            {favorites.map((t, i) => (
              <TopicRow key={t.id} topic={t} first={i === 0} onOpen={onOpen} onStar={toggleFavorite} />
            ))}
          </Card>
        </>
      ) : null}

      {others.length > 0 ? (
        <>
          <SectionLabel>Other topics</SectionLabel>
          <Card>
            {others.map((t, i) => (
              <TopicRow key={t.id} topic={t} first={i === 0} onOpen={onOpen} onStar={toggleFavorite} />
            ))}
          </Card>
          <Hint>Other topics have no text waiting, so opening one takes about half a minute.</Hint>
        </>
      ) : null}

      <SectionLabel>New topic</SectionLabel>
      <View style={[styles.field, { backgroundColor: c.card }]}>
        <TextInput
          style={[styles.input, { color: c.text }]}
          placeholder="e.g. Asking for directions"
          placeholderTextColor={c.textTertiary}
          value={newName}
          onChangeText={setNewName}
          onSubmitEditing={add}
          returnKeyType="done"
        />
        <PillButton label="Add" onPress={add} />
      </View>
      <Hint>New topics start as favorites, so a text is written for them right away.</Hint>
    </ScrollView>
  );
}

function TopicRow({
  topic,
  first,
  onOpen,
  onStar,
}: {
  topic: Topic;
  first: boolean;
  onOpen: (t: Topic) => void;
  onStar: (t: Topic) => void;
}) {
  const c = useColors();
  return (
    <Pressable
      onPress={() => onOpen(topic)}
      accessibilityRole="button"
      style={({ pressed }) => [styles.row, { opacity: pressed ? 0.7 : 1 }]}
    >
      <Pressable
        onPress={() => onStar(topic)}
        hitSlop={10}
        accessibilityRole="button"
        accessibilityLabel={topic.favorite ? `Remove ${topic.name} from favorites` : `Add ${topic.name} to favorites`}
      >
        <Text style={[styles.star, { color: topic.favorite ? c.accent : c.textTertiary }]}>
          {topic.favorite ? "★" : "☆"}
        </Text>
      </Pressable>
      <View style={[styles.rowBody, !first && { borderTopWidth: StyleSheet.hairlineWidth, borderTopColor: c.separator }]}>
        <Text style={[styles.name, { color: c.text }]}>{topic.name}</Text>
        {topic.ready > 0 ? (
          <Text style={[styles.ready, { backgroundColor: c.speakerB, color: c.speakerBText }]}>Ready</Text>
        ) : topic.favorite ? (
          <View style={styles.writing}>
            <ActivityIndicator size="small" />
            <Text style={[styles.writingText, { color: c.textTertiary }]}>Writing a text</Text>
          </View>
        ) : null}
        <Text style={[styles.chevron, { color: c.textTertiary }]}>›</Text>
      </View>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  content: { paddingTop: spacing.sm, paddingBottom: spacing.xl },
  title: { fontSize: font.title, fontWeight: "700", paddingHorizontal: spacing.md },
  sub: { fontSize: font.md, paddingHorizontal: spacing.md, paddingTop: spacing.xs },
  loading: { marginTop: spacing.xl },
  row: { flexDirection: "row", alignItems: "center", paddingLeft: spacing.md, gap: spacing.smd },
  rowBody: {
    flex: 1,
    flexDirection: "row",
    alignItems: "center",
    minHeight: 52,
    paddingVertical: spacing.smd,
    paddingRight: spacing.md,
    gap: spacing.sm,
  },
  star: { fontSize: font.lg },
  name: { flex: 1, fontSize: font.lg },
  ready: {
    fontSize: font.sm,
    fontWeight: "600",
    paddingHorizontal: 10,
    paddingVertical: spacing.xs,
    borderRadius: radius.full,
    overflow: "hidden",
  },
  writing: { flexDirection: "row", alignItems: "center", gap: spacing.xs },
  writingText: { fontSize: font.md },
  chevron: { fontSize: font.xl },
  field: {
    flexDirection: "row",
    alignItems: "center",
    marginHorizontal: spacing.md,
    borderRadius: radius.md,
    paddingLeft: spacing.md,
    paddingRight: spacing.sm,
    minHeight: 52,
    gap: spacing.sm,
  },
  input: { flex: 1, fontSize: font.lg, minHeight: 44 },
});
