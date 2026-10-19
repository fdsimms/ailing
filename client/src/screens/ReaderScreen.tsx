// The reader: a dialogue split into words by the server, a gloss on tap, and a rating at the end.
// Audio comes with the audio PR; until then this is read-only.
//
// ==== Layout ====
// NavBar, title, practice words, the Show English switch, the lines, then a Done button. "Done"
// swaps the lines for the end view (rating, stats, words marked unknown). The gloss popover is a
// transparent Modal, so a tap's page coordinates place it directly.
import { useEffect, useRef, useState } from "react";
import {
  ActivityIndicator,
  Modal,
  Pressable,
  ScrollView,
  StyleSheet,
  Switch,
  Text,
  useWindowDimensions,
  View,
} from "react-native";

import { type Api, ApiError, type Rating, type ReaderText, type Topic, type Word } from "../api";
import { Card, ErrorNote, Hint, NavBar, PillButton, PrimaryButton, SectionLabel, TextButton } from "../components/ui";
import { formatDuration, isFlagged, lookUp, type Session, startSession, toLog, toggleFlag } from "../session";
import { font, radius, spacing, thaiFont, useColors } from "../theme";

type Tapped = { word: Word; x: number; y: number };

export function ReaderScreen({ api, topic, onBack }: { api: Api; topic: Topic; onBack: () => void }) {
  const c = useColors();
  const [text, setText] = useState<ReaderText | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [session, setSession] = useState<Session | null>(null);
  const [english, setEnglish] = useState(false);
  const [tapped, setTapped] = useState<Tapped | null>(null);
  const [ended, setEnded] = useState(false);
  const [rating, setRating] = useState<Rating | null>(null);
  const [leaving, setLeaving] = useState(false);
  const logged = useRef(false);

  async function load() {
    setText(null);
    setError(null);
    setEnded(false);
    setRating(null);
    logged.current = false;
    try {
      const next = await api.nextText(topic.id);
      setText(next);
      setSession(startSession(next, Date.now()));
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Couldn't get a text. Try again.");
    }
  }

  useEffect(() => {
    load();
    // Loads once per topic; `load` itself is recreated each render.
  }, [topic.id]);

  // Every way out of a text logs it once, which also takes it off the ready queue.
  async function finish(then: "next" | "back") {
    if (text && session && !logged.current) {
      logged.current = true;
      setLeaving(true);
      try {
        await api.logReading(text.id, toLog(session, Date.now(), rating, ended));
      } catch {
        // The reading is lost, not the user's place: carry on either way.
      } finally {
        setLeaving(false);
      }
    }
    if (then === "next") load();
    else onBack();
  }

  function tap(word: Word, x: number, y: number) {
    if (!session) return;
    setSession(lookUp(session, word.text));
    setTapped({ word, x, y });
  }

  const seconds = session ? Math.round((Date.now() - session.startedAt) / 1000) : 0;

  return (
    <View style={styles.root}>
      <NavBar back="Topics" title={topic.name} onBack={() => finish("back")} />
      {error ? <ErrorNote message={error} onRetry={load} /> : null}
      {!text && !error ? (
        <View style={styles.loading}>
          <ActivityIndicator />
          <Text style={[styles.loadingText, { color: c.textSecondary }]}>
            {topic.ready > 0 ? "Opening the text" : "Writing a text. This takes about half a minute."}
          </Text>
        </View>
      ) : null}

      {text && session && !ended ? (
        <ScrollView contentContainerStyle={styles.content}>
          <Text style={[styles.title, { color: c.text }]}>{text.title}</Text>
          {text.stretch.length > 0 ? (
            <View style={styles.practice}>
              <Text style={[styles.practiceLabel, { color: c.textSecondary }]}>Practice words:</Text>
              {text.stretch.map((w) => (
                <Text key={w} style={[styles.chip, { backgroundColor: c.accentSubtle, color: c.accentText }]}>
                  {w}
                </Text>
              ))}
            </View>
          ) : null}
          <View style={styles.toggle}>
            <Text style={[styles.toggleText, { color: c.textSecondary }]}>Show English</Text>
            <Switch value={english} onValueChange={setEnglish} trackColor={{ true: c.accent }} />
          </View>
          {text.lines.map((line, i) => (
            <View key={i} style={[styles.line, { borderBottomColor: c.separator }]}>
              <Text
                style={[
                  styles.speaker,
                  line.speaker === "A"
                    ? { backgroundColor: c.accentSubtle, color: c.accentText }
                    : { backgroundColor: c.speakerB, color: c.speakerBText },
                ]}
              >
                {line.speaker}
              </Text>
              <View style={styles.lineBody}>
                <View style={styles.words}>
                  {line.words.map((word, j) => (
                    <WordView
                      key={j}
                      word={word}
                      flagged={isFlagged(session, word.text)}
                      selected={tapped?.word === word}
                      onPress={tap}
                    />
                  ))}
                </View>
                {english ? <Text style={[styles.english, { color: c.textSecondary }]}>{line.english}</Text> : null}
              </View>
            </View>
          ))}
          <View style={styles.doneButton}>
            <PrimaryButton label="Done" onPress={() => setEnded(true)} />
          </View>
        </ScrollView>
      ) : null}

      {text && session && ended ? (
        <ScrollView contentContainerStyle={styles.content}>
          <Card>
            <View style={styles.endCard}>
              <Text style={[styles.endTitle, { color: c.text }]}>How was this one?</Text>
              <Text style={[styles.endSub, { color: c.textSecondary }]}>Your answer sets how hard the next text is.</Text>
              {RATINGS.map((r) => (
                <Pressable
                  key={r.value}
                  onPress={() => setRating(rating === r.value ? null : r.value)}
                  accessibilityRole="radio"
                  accessibilityState={{ selected: rating === r.value }}
                  style={[
                    styles.rating,
                    { borderColor: rating === r.value ? c.accent : c.separator },
                    rating === r.value && { backgroundColor: c.accentSubtle },
                  ]}
                >
                  <Text style={[styles.ratingLabel, { color: rating === r.value ? c.accentText : c.text }]}>{r.label}</Text>
                  <Text style={[styles.ratingHint, { color: rating === r.value ? c.accentText : c.textTertiary }]}>{r.hint}</Text>
                </Pressable>
              ))}
            </View>
          </Card>
          <View style={styles.stats}>
            <Stat value={`${Math.round(text.coverage * 100)}%`} label="Words you know" />
            <Stat value={String(session.glossed.length)} label="Words looked up" />
            <Stat value={formatDuration(seconds)} label="Time" />
          </View>
          {session.flagged.length > 0 ? (
            <>
              <SectionLabel>Marked as unknown</SectionLabel>
              <Card>
                {session.flagged.map((w, i) => (
                  <View
                    key={w}
                    style={[styles.flaggedRow, i > 0 && { borderTopWidth: StyleSheet.hairlineWidth, borderTopColor: c.separator }]}
                  >
                    <Text style={[styles.flaggedWord, { color: c.text }]}>{w}</Text>
                    <Text style={[styles.flaggedGloss, { color: c.textSecondary }]}>{glossFor(text, w) ?? ""}</Text>
                  </View>
                ))}
              </Card>
              <Hint>Marked words are only saved for now. Nothing is added to Anki.</Hint>
            </>
          ) : null}
          <View style={styles.endButtons}>
            <PrimaryButton label="Next text" onPress={() => finish("next")} busy={leaving} />
            <TextButton label="Back to topics" onPress={() => finish("back")} />
          </View>
        </ScrollView>
      ) : null}

      <GlossPopover
        tapped={tapped}
        flagged={tapped && session ? isFlagged(session, tapped.word.text) : false}
        onToggleFlag={() => tapped && session && setSession(toggleFlag(session, tapped.word.text))}
        onClose={() => setTapped(null)}
      />
    </View>
  );
}

const RATINGS: { value: Rating; label: string; hint: string }[] = [
  { value: "too_easy", label: "Too easy", hint: "More new words next time" },
  { value: "about_right", label: "About right", hint: "Keep it like this" },
  { value: "too_hard", label: "Too hard", hint: "Fewer new words next time" },
];

function glossFor(text: ReaderText, word: string): string | null {
  for (const line of text.lines) for (const w of line.words) if (w.text === word && w.gloss) return w.gloss;
  return null;
}

function WordView({
  word,
  flagged,
  selected,
  onPress,
}: {
  word: Word;
  flagged: boolean;
  selected: boolean;
  onPress: (word: Word, x: number, y: number) => void;
}) {
  const c = useColors();
  if (word.status === null) {
    // A space becomes a gap; punctuation is shown but can't be tapped.
    return word.text.trim() ? (
      <Text style={[styles.thai, { color: c.text }]}>{word.text}</Text>
    ) : (
      <View style={styles.space} />
    );
  }
  return (
    <Pressable
      onPress={(e) => onPress(word, e.nativeEvent.pageX, e.nativeEvent.pageY)}
      accessibilityRole="button"
      accessibilityHint="Shows what this word means"
      style={[
        styles.word,
        selected && { backgroundColor: c.accentSubtle, borderColor: c.accent },
      ]}
    >
      <Text
        style={[
          styles.thai,
          { color: word.stretch ? c.accentText : c.text },
          word.stretch && styles.stretch,
          (word.stretch || flagged) && {
            textDecorationLine: "underline",
            textDecorationStyle: "dotted",
            textDecorationColor: flagged ? c.red : c.accent,
          },
        ]}
      >
        {word.text}
      </Text>
    </Pressable>
  );
}

const POPOVER_WIDTH = 290;

function GlossPopover({
  tapped,
  flagged,
  onToggleFlag,
  onClose,
}: {
  tapped: Tapped | null;
  flagged: boolean;
  onToggleFlag: () => void;
  onClose: () => void;
}) {
  const c = useColors();
  const { width, height } = useWindowDimensions();
  if (!tapped) return null;
  const left = Math.min(Math.max(tapped.x - 40, spacing.md), width - POPOVER_WIDTH - spacing.md);
  // Above the word when there's room, so the finger and the word both stay visible.
  const place = tapped.y > 260 ? { bottom: height - tapped.y + 28 } : { top: tapped.y + 28 };
  const status =
    tapped.word.status === "known"
      ? "In your deck"
      : tapped.word.status === "partial"
        ? "Only inside a longer phrase in your deck"
        : "Not in your deck";
  return (
    <Modal visible transparent animationType="fade" onRequestClose={onClose}>
      <Pressable style={StyleSheet.absoluteFill} onPress={onClose} accessibilityLabel="Close" />
      <View
        style={[
          styles.popover,
          place,
          { left, backgroundColor: c.card, borderColor: c.separator, shadowColor: c.shadow },
        ]}
      >
        <Text style={[styles.popWord, { color: c.text }]}>{tapped.word.text}</Text>
        <Text style={[styles.popGloss, { color: c.text }]}>{tapped.word.gloss ?? "No meaning available"}</Text>
        <Text style={[styles.popStatus, { color: c.textSecondary }]}>{status}</Text>
        <View style={styles.popActions}>
          <PillButton label={flagged ? "Unmark" : "Mark as unknown"} onPress={onToggleFlag} />
        </View>
      </View>
    </Modal>
  );
}

function Stat({ value, label }: { value: string; label: string }) {
  const c = useColors();
  return (
    <View style={[styles.stat, { backgroundColor: c.card }]}>
      <Text style={[styles.statValue, { color: c.text }]}>{value}</Text>
      <Text style={[styles.statLabel, { color: c.textSecondary }]}>{label}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1 },
  loading: { padding: spacing.xl, alignItems: "center", gap: spacing.smd },
  loadingText: { fontSize: font.md, textAlign: "center" },
  content: { paddingBottom: spacing.xl },
  title: { fontSize: font.xxl, fontWeight: "700", paddingHorizontal: spacing.md, paddingTop: spacing.xs },
  practice: {
    flexDirection: "row",
    flexWrap: "wrap",
    alignItems: "center",
    gap: spacing.sm,
    paddingHorizontal: spacing.md,
    paddingTop: spacing.sm,
  },
  practiceLabel: { fontSize: font.sm },
  chip: {
    fontSize: font.md,
    fontWeight: "700",
    paddingHorizontal: 10,
    paddingVertical: 3,
    borderRadius: radius.full,
    overflow: "hidden",
  },
  toggle: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "center",
    paddingHorizontal: spacing.md,
    paddingTop: spacing.md,
    paddingBottom: spacing.sm,
  },
  toggleText: { fontSize: font.md },
  line: {
    flexDirection: "row",
    gap: 10,
    marginHorizontal: spacing.md,
    paddingVertical: spacing.smd,
    borderBottomWidth: StyleSheet.hairlineWidth,
  },
  speaker: {
    width: 26,
    height: 26,
    borderRadius: 13,
    overflow: "hidden",
    textAlign: "center",
    lineHeight: 26,
    fontSize: font.sm,
    fontWeight: "700",
    marginTop: 8,
  },
  lineBody: { flex: 1 },
  words: { flexDirection: "row", flexWrap: "wrap", alignItems: "center" },
  word: {
    borderRadius: 6,
    borderWidth: 1.5,
    borderColor: "transparent",
    paddingHorizontal: 1,
    marginRight: 3,
  },
  space: { width: 8 },
  thai: { fontSize: thaiFont, lineHeight: thaiFont * 1.75 },
  stretch: { fontWeight: "700" },
  english: { fontSize: 14, lineHeight: 18, marginTop: 2 },
  doneButton: { padding: spacing.md, paddingTop: spacing.lg },
  endCard: { padding: spacing.md, gap: spacing.sm },
  endTitle: { fontSize: 22, fontWeight: "700" },
  endSub: { fontSize: font.md, marginBottom: spacing.sm },
  rating: {
    borderWidth: 1,
    borderRadius: radius.md,
    paddingHorizontal: spacing.md,
    paddingVertical: 14,
    gap: 2,
  },
  ratingLabel: { fontSize: font.lg, fontWeight: "600" },
  ratingHint: { fontSize: font.sm },
  stats: { flexDirection: "row", gap: spacing.sm, margin: spacing.md },
  stat: { flex: 1, borderRadius: radius.md, padding: spacing.smd },
  statValue: { fontSize: 22, fontWeight: "700" },
  statLabel: { fontSize: font.xs, marginTop: 2 },
  flaggedRow: { flexDirection: "row", alignItems: "center", gap: spacing.smd, padding: spacing.md },
  flaggedWord: { fontSize: font.lg },
  flaggedGloss: { flex: 1, fontSize: font.md },
  endButtons: { padding: spacing.md, paddingTop: spacing.lg, gap: spacing.xs },
  popover: {
    position: "absolute",
    width: POPOVER_WIDTH,
    borderRadius: radius.lg,
    borderWidth: StyleSheet.hairlineWidth,
    padding: spacing.md,
    shadowOpacity: 1,
    shadowRadius: 15,
    shadowOffset: { width: 0, height: 8 },
  },
  popWord: { fontSize: font.xxl, fontWeight: "700" },
  popGloss: { fontSize: font.lg, marginTop: 2 },
  popStatus: { fontSize: font.sm, marginTop: 6 },
  popActions: { flexDirection: "row", gap: spacing.sm, marginTop: 14 },
});
