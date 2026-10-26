import { useCallback, useEffect, useState } from "react";
import {
  ActivityIndicator,
  Alert,
  Pressable,
  RefreshControl,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  View,
} from "react-native";

import { type Api, ApiError, type Progress, type StretchWords, type Topic } from "../api";
import { Card, ErrorNote, Hint, PillButton, SectionLabel, Segments, TextButton } from "../components/ui";
import { describeProgress } from "../progress";
import { font, radius, spacing, useColors } from "../theme";

// While a favorite is still being written, check back this often.
const WRITING_POLL_MS = 10_000;

export function TopicsScreen({
  api,
  onOpen,
  onWords,
  onLogOut,
}: {
  api: Api;
  onOpen: (topic: Topic) => void;
  onWords: () => void;
  onLogOut: () => void;
}) {
  const c = useColors();
  const [topics, setTopics] = useState<Topic[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [refreshing, setRefreshing] = useState(false);
  const [newName, setNewName] = useState("");
  const [adding, setAdding] = useState(false);
  const [addError, setAddError] = useState<string | null>(null);
  const [stretchWords, setStretchWords] = useState<StretchWords | null>(null);
  const [settingError, setSettingError] = useState<string | null>(null);
  const [progress, setProgress] = useState<Progress | null>(null);
  const [markedCount, setMarkedCount] = useState<number | null>(null);

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

  // Loaded apart from the topics, and left out quietly if they fail.
  const loadExtras = useCallback(async () => {
    await Promise.all([
      api.progress().then(setProgress, () => {}),
      api.markedWords().then((ws) => setMarkedCount(ws.length), () => {}),
    ]);
  }, [api]);

  useEffect(() => {
    loadExtras();
  }, [loadExtras]);

  // Loaded on its own, so the topics still show if this fails.
  useEffect(() => {
    api.settings().then(
      (s) => setStretchWords(s.stretch_words),
      () => {},
    );
  }, [api]);

  async function changeStretchWords(value: StretchWords) {
    const before = stretchWords;
    setStretchWords(value);
    setSettingError(null);
    try {
      setStretchWords((await api.updateSettings({ stretch_words: value })).stretch_words);
    } catch (e) {
      setStretchWords(before);
      setSettingError(e instanceof ApiError ? e.message : "Couldn't change that setting. Try again.");
    }
  }

  // Poll only while the server says a text is being written; a failed write stops it.
  const writing = topics?.some((t) => t.state === "writing") ?? false;
  useEffect(() => {
    if (!writing) return;
    const id = setInterval(load, WRITING_POLL_MS);
    return () => clearInterval(id);
  }, [writing, load]);

  async function add() {
    const name = newName.trim();
    if (!name || adding) return;
    setAdding(true);
    setAddError(null);
    try {
      await api.addTopic(name);
      setNewName("");
      await load();
    } catch (e) {
      setAddError(e instanceof ApiError ? e.message : "Couldn't add that topic. Try again.");
    } finally {
      setAdding(false);
    }
  }

  function confirmRemove(topic: Topic) {
    Alert.alert(`Remove ${topic.name}?`, "It leaves your list. Adding a topic with the same name brings it back.", [
      { text: "Cancel", style: "cancel" },
      { text: "Remove", style: "destructive", onPress: () => remove(topic) },
    ]);
  }

  async function remove(topic: Topic) {
    setTopics((ts) => ts?.filter((t) => t.id !== topic.id) ?? ts);
    try {
      await api.removeTopic(topic.id);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Couldn't remove that topic.");
    }
    await load();
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
            await Promise.all([load(), loadExtras()]);
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

      {progress ? <ProgressCard progress={progress} /> : null}

      {favorites.length > 0 ? (
        <>
          <SectionLabel>Favorites</SectionLabel>
          <Card>
            {favorites.map((t, i) => (
              <TopicRow
                key={t.id}
                topic={t}
                first={i === 0}
                onOpen={onOpen}
                onStar={toggleFavorite}
                onRemove={confirmRemove}
              />
            ))}
          </Card>
        </>
      ) : null}

      {others.length > 0 ? (
        <>
          <SectionLabel>Other topics</SectionLabel>
          <Card>
            {others.map((t, i) => (
              <TopicRow
                key={t.id}
                topic={t}
                first={i === 0}
                onOpen={onOpen}
                onStar={toggleFavorite}
                onRemove={confirmRemove}
              />
            ))}
          </Card>
          <Hint>Opening a topic with no text ready takes about half a minute.</Hint>
        </>
      ) : null}
      {topics && topics.length > 0 ? <Hint>Press and hold a topic to remove it.</Hint> : null}

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
        {adding ? <ActivityIndicator style={styles.adding} /> : <PillButton label="Add" onPress={add} />}
      </View>
      {addError ? <ErrorNote message={addError} /> : null}
      <Hint>New topics start as favorites, so a text is written for them right away.</Hint>
      <SectionLabel>Your words</SectionLabel>
      <Card>
        <Pressable
          onPress={onWords}
          accessibilityRole="button"
          accessibilityLabel={markedCount === null ? "Marked words" : `Marked words, ${markedCount}`}
          style={({ pressed }) => [styles.rowBody, styles.wordsRow, { opacity: pressed ? 0.7 : 1 }]}
        >
          <Text style={[styles.name, { color: c.text }]}>Marked words</Text>
          {markedCount !== null ? (
            <Text style={[styles.writingText, { color: c.textSecondary }]}>{markedCount}</Text>
          ) : null}
          <Text style={[styles.chevron, { color: c.textTertiary }]}>›</Text>
        </Pressable>
      </Card>
      {stretchWords ? (
        <>
          <SectionLabel>Stretch words</SectionLabel>
          <Segments
            style={styles.segments}
            options={[
              { value: "topic", label: "Fit the topic" },
              { value: "any", label: "Any due word" },
            ]}
            value={stretchWords}
            onChange={changeStretchWords}
          />
          {settingError ? <ErrorNote message={settingError} /> : null}
          <Hint>{STRETCH_HINT[stretchWords]}</Hint>
        </>
      ) : null}
      <View style={styles.logOut}>
        <TextButton label="Log out" onPress={onLogOut} />
      </View>
    </ScrollView>
  );
}

function ProgressCard({ progress }: { progress: Progress }) {
  const c = useColors();
  const { headline, detail, next } = describeProgress(progress);
  return (
    <>
      <SectionLabel>Progress</SectionLabel>
      <Card>
        <View style={styles.progress}>
          <Text style={[styles.progressHeadline, { color: c.text }]}>{headline}</Text>
          <Text style={[styles.progressDetail, { color: c.textSecondary }]}>{detail}</Text>
          <Text style={[styles.progressNext, { color: c.textTertiary }]}>{next}</Text>
        </View>
      </Card>
    </>
  );
}

function TopicRow({
  topic,
  first,
  onOpen,
  onStar,
  onRemove,
}: {
  topic: Topic;
  first: boolean;
  onOpen: (t: Topic) => void;
  onStar: (t: Topic) => void;
  onRemove: (t: Topic) => void;
}) {
  const c = useColors();
  const state = STATE_TEXT[topic.state];
  // The star and the row are siblings, so VoiceOver can reach each one on its own.
  return (
    <View style={styles.row}>
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
      <Pressable
        onPress={() => onOpen(topic)}
        onLongPress={() => onRemove(topic)}
        accessibilityActions={[{ name: "remove", label: "Remove topic" }]}
        onAccessibilityAction={(e) => e.nativeEvent.actionName === "remove" && onRemove(topic)}
        accessibilityRole="button"
        accessibilityLabel={state ? `${topic.name}, ${state}` : topic.name}
        accessibilityHint="Opens a text on this topic"
        style={({ pressed }) => [
          styles.rowBody,
          !first && { borderTopWidth: StyleSheet.hairlineWidth, borderTopColor: c.separator },
          { opacity: pressed ? 0.7 : 1 },
        ]}
      >
        <Text style={[styles.name, { color: c.text }]}>{topic.name}</Text>
        {topic.state === "ready" ? (
          <Text style={[styles.ready, { backgroundColor: c.speakerB, color: c.speakerBText }]}>Ready</Text>
        ) : topic.state === "writing" ? (
          <View style={styles.writing}>
            <ActivityIndicator size="small" />
            <Text style={[styles.writingText, { color: c.textTertiary }]}>Writing a text</Text>
          </View>
        ) : topic.state === "failed" ? (
          <Text style={[styles.writingText, { color: c.textSecondary }]}>Couldn't write one</Text>
        ) : null}
        <Text style={[styles.chevron, { color: c.textTertiary }]}>›</Text>
      </Pressable>
    </View>
  );
}

const STRETCH_HINT: Record<StretchWords, string> = {
  topic: "Picked from your due and newer cards to fit the topic. Applies from the next text written.",
  any: "Any of your due and newer cards, even ones that don't fit the topic. Applies from the next text written.",
};

const STATE_TEXT: Record<Topic["state"], string | null> = {
  ready: "ready",
  writing: "writing a text",
  failed: "couldn't write one",
  idle: null,
};

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
  adding: { marginHorizontal: spacing.smd },
  segments: { marginHorizontal: spacing.md },
  logOut: { marginTop: spacing.lg },
  wordsRow: { paddingLeft: spacing.md },
  progress: { padding: spacing.md, gap: spacing.xs },
  progressHeadline: { fontSize: font.lg, fontWeight: "600" },
  progressDetail: { fontSize: font.md, lineHeight: 21 },
  progressNext: { fontSize: font.sm, lineHeight: 18 },
});
