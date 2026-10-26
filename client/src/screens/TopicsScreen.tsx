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

import {
  type Api,
  ApiError,
  type Form,
  type Language,
  type Length,
  type Progress,
  type Settings,
  type StretchWords,
  type Suggestion,
  type Topic,
} from "../api";
import { Card, ErrorNote, Hint, PillButton, SectionLabel, Segments, TextButton } from "../components/ui";
import { ideaPage } from "../ideas";
import { LANGUAGE_ORDER, LANGUAGES } from "../languages";
import { describeProgress } from "../progress";
import { font, radius, spacing, useColors } from "../theme";

// While a favorite is still being written, check back this often.
const WRITING_POLL_MS = 10_000;

export function TopicsScreen({
  api,
  onOpen,
  onWords,
  onPast,
  onLogOut,
}: {
  api: Api;
  onOpen: (topic: Topic) => void;
  onWords: () => void;
  onPast: () => void;
  onLogOut: () => void;
}) {
  const c = useColors();
  const [topics, setTopics] = useState<Topic[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [refreshing, setRefreshing] = useState(false);
  const [newName, setNewName] = useState("");
  const [adding, setAdding] = useState(false);
  const [addError, setAddError] = useState<string | null>(null);
  const [settings, setSettings] = useState<Settings | null>(null);
  const [settingError, setSettingError] = useState<string | null>(null);
  const [progress, setProgress] = useState<Progress | null>(null);
  const [markedCount, setMarkedCount] = useState<number | null>(null);
  const [ideas, setIdeas] = useState<Suggestion[]>([]);
  const [ideaPageIndex, setIdeaPageIndex] = useState(0);
  const [opening, setOpening] = useState<string | null>(null);

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
      api.suggestions().then(setIdeas, () => {}),
    ]);
  }, [api]);

  useEffect(() => {
    loadExtras();
  }, [loadExtras]);

  // Loaded on its own, so the topics still show if this fails.
  useEffect(() => {
    api.settings().then(setSettings, () => {});
  }, [api]);

  // Whether the server took the change.
  async function changeSetting(change: Partial<Settings>): Promise<boolean> {
    const before = settings;
    setSettings((s) => (s ? { ...s, ...change } : s));
    setSettingError(null);
    try {
      setSettings(await api.updateSettings(change));
      return true;
    } catch (e) {
      setSettings(before);
      setSettingError(e instanceof ApiError ? e.message : "Couldn't change that setting. Try again.");
      return false;
    }
  }

  // Topics are shared by both languages; everything else on this screen is the chosen one's.
  async function changeLanguage(language: Language) {
    if (await changeSetting({ language })) {
      setIdeaPageIndex(0);
      await Promise.all([load(), loadExtras()]);
    }
  }

  // Poll only while the server says a text is being written; a failed write stops it.
  const writing = topics?.some((t) => t.state === "writing") ?? false;
  useEffect(() => {
    if (!writing) return;
    const id = setInterval(load, WRITING_POLL_MS);
    return () => clearInterval(id);
  }, [writing, load]);

  // An idea opens straight away, as a topic that isn't a favorite, so trying one doesn't start a
  // queue of texts for it. Starring it afterwards does.
  async function openIdea(name: string) {
    if (opening) return;
    setOpening(name);
    setAddError(null);
    try {
      const topic = await api.addTopic(name, false);
      onOpen(topic);
    } catch (e) {
      setAddError(e instanceof ApiError ? e.message : "Couldn't open that topic. Try again.");
      setOpening(null);
    }
  }

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
        {`Pick a topic. Texts use words from your ${LANGUAGES[settings?.language ?? "th"].name} deck.`}
      </Text>
      {settings ? (
        <Segments<Language>
          style={styles.language}
          options={LANGUAGE_ORDER.map((code) => ({ value: code, label: LANGUAGES[code].name }))}
          value={settings.language}
          onChange={changeLanguage}
        />
      ) : null}

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

      {ideas.length > 0 ? (
        <>
          <SectionLabel>Ideas</SectionLabel>
          <View style={styles.ideas}>
            {ideaPage(ideas, ideaPageIndex).map((idea) => (
              <Pressable
                key={idea.name}
                onPress={() => openIdea(idea.name)}
                disabled={opening !== null}
                accessibilityRole="button"
                accessibilityHint="Opens a text on this topic"
                style={({ pressed }) => [
                  styles.idea,
                  { backgroundColor: c.card, opacity: pressed || (opening && opening !== idea.name) ? 0.6 : 1 },
                ]}
              >
                {opening === idea.name ? <ActivityIndicator size="small" /> : null}
                <Text style={[styles.ideaText, { color: c.text }]}>{idea.name}</Text>
              </Pressable>
            ))}
          </View>
          {ideas.length > ideaPage(ideas, 0).length ? (
            <TextButton label="More ideas" onPress={() => setIdeaPageIndex((p) => p + 1)} />
          ) : null}
          <Hint>
            {`${settings?.language === "es" ? "" : "Ideas that use more of your deck come first. "}Tap one to read about it, and star it to keep texts coming.`}
          </Hint>
        </>
      ) : null}

      <SectionLabel>New topic</SectionLabel>
      <View style={[styles.field, { backgroundColor: c.card }]}>
        <TextInput
          style={[styles.input, { color: c.text }]}
          placeholder="Type your own"
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
      <SectionLabel>Your reading</SectionLabel>
      <Card>
        <Pressable
          onPress={onPast}
          accessibilityRole="button"
          accessibilityHint="Read or listen to a text again"
          style={({ pressed }) => [styles.rowBody, styles.wordsRow, { opacity: pressed ? 0.7 : 1 }]}
        >
          <Text style={[styles.name, { color: c.text }]}>Past texts</Text>
          <Text style={[styles.chevron, { color: c.textTertiary }]}>›</Text>
        </Pressable>
        <Pressable
          onPress={onWords}
          accessibilityRole="button"
          accessibilityLabel={markedCount === null ? "Marked words" : `Marked words, ${markedCount}`}
          style={({ pressed }) => [
            styles.rowBody,
            styles.wordsRow,
            { borderTopWidth: StyleSheet.hairlineWidth, borderTopColor: c.separator },
            { opacity: pressed ? 0.7 : 1 },
          ]}
        >
          <Text style={[styles.name, { color: c.text }]}>Marked words</Text>
          {markedCount !== null ? (
            <Text style={[styles.writingText, { color: c.textSecondary }]}>{markedCount}</Text>
          ) : null}
          <Text style={[styles.chevron, { color: c.textTertiary }]}>›</Text>
        </Pressable>
      </Card>
      {settings ? (
        <>
          <SectionLabel>Text type</SectionLabel>
          <Segments<Form>
            style={styles.segments}
            options={[
              { value: "dialogue", label: "Dialogue" },
              { value: "story", label: "Short story" },
            ]}
            value={settings.form}
            onChange={(form) => changeSetting({ form })}
          />
          <Hint>{FORM_HINT[settings.form]}</Hint>
          <SectionLabel>Length</SectionLabel>
          <Segments<Length>
            style={styles.segments}
            options={[
              { value: 6, label: "Short" },
              { value: 8, label: "Medium" },
              { value: 12, label: "Long" },
            ]}
            value={settings.lines}
            onChange={(lines) => changeSetting({ lines })}
          />
          <Hint>{`${settings.lines} lines. Applies from the next text written.`}</Hint>
          <SectionLabel>Stretch words</SectionLabel>
          <Segments<StretchWords>
            style={styles.segments}
            options={[
              { value: "topic", label: "Fit the topic" },
              { value: "any", label: "Any due word" },
            ]}
            value={settings.stretch_words}
            onChange={(stretch_words) => changeSetting({ stretch_words })}
          />
          {settingError ? <ErrorNote message={settingError} /> : null}
          <Hint>{STRETCH_HINT[settings.stretch_words]}</Hint>
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

const FORM_HINT: Record<Form, string> = {
  dialogue: "Two people talking. Applies from the next text written.",
  story:
    "A short story told by a narrator. Stories describe more, so they're a little harder to fit to your deck. Applies from the next text written.",
};

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
  language: { marginHorizontal: spacing.md, marginTop: spacing.md },
  logOut: { marginTop: spacing.lg },
  wordsRow: { paddingLeft: spacing.md },
  ideas: { flexDirection: "row", flexWrap: "wrap", gap: spacing.sm, paddingHorizontal: spacing.md },
  idea: {
    flexDirection: "row",
    alignItems: "center",
    gap: spacing.xs,
    borderRadius: radius.full,
    paddingHorizontal: spacing.smd,
    paddingVertical: spacing.sm,
  },
  ideaText: { fontSize: font.md },
  progress: { padding: spacing.md, gap: spacing.xs },
  progressHeadline: { fontSize: font.lg, fontWeight: "600" },
  progressDetail: { fontSize: font.md, lineHeight: 21 },
  progressNext: { fontSize: font.sm, lineHeight: 18 },
});
