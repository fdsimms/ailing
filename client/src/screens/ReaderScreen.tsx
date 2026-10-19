// The reader: a dialogue split into words by the server, a gloss on tap, audio line by line, and a
// rating at the end.
//
// ==== Layout ====
// NavBar, title, practice words, the Show English switch, the lines (each with its own replay
// button), then a Done button, with the player bar pinned under the scroll view. "Done" swaps the
// lines for the end view (rating, stats, words marked unknown). The gloss popover is a transparent
// Modal, so a tap's page coordinates place it directly.
//
// ==== Audio ====
// One expo-audio player is reused for every line. "Play" runs the dialogue from the current line to
// the end (`nextLine` in playback.ts); a line's replay button plays that line alone. Speed is the
// player's rate, with pitch kept, so each line is one file whatever the speed. The audio session
// stays active between lines (`keepAudioSessionActive`): expo-audio otherwise drops it after each
// line, and with the screen locked iOS can suspend the app before the next line starts. A line that
// fails to load counts as finished, so "Play" moves on instead of stalling.
//
// ==== Loading ====
// `/next` answers 202 while the server writes a text, so `load` asks again every few seconds.
// `loadId` and `mounted` make a load that's been superseded (Next, then Back) drop its result.
import { useAudioPlayer, useAudioPlayerStatus } from "expo-audio";
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
import { useSafeAreaInsets } from "react-native-safe-area-context";

import { type Api, ApiError, type Rating, type ReaderText, type Topic, type Word } from "../api";
import {
  Card,
  ErrorNote,
  Hint,
  NavBar,
  PillButton,
  PrimaryButton,
  SectionLabel,
  Segments,
  TextButton,
} from "../components/ui";
import { firstLine, nextLine } from "../playback";
import { RATES } from "../playbackRate";
import { formatDuration, heard, isFlagged, lookUp, type Session, startSession, toLog, toggleFlag } from "../session";
import { font, radius, spacing, thaiFont, useColors } from "../theme";

type Tapped = { word: Word; x: number; y: number };

// The speed chosen last, kept for the rest of the app's run.
let lastRate = 0.9;

const POLL_MS = 3_000;
// Three attempts and the audio rarely take more than two minutes; past this, something is wrong.
const WRITE_WAIT_MS = 4 * 60_000;

const wait = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));

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
  const [writing, setWriting] = useState(false);
  const logged = useRef(false);
  const mounted = useRef(true);
  const loadId = useRef(0);
  useEffect(
    () => () => {
      mounted.current = false;
    },
    [],
  );

  const player = useAudioPlayer(null, { keepAudioSessionActive: true });
  const status = useAudioPlayerStatus(player);
  const [current, setCurrent] = useState<number | null>(null);
  const [playingAll, setPlayingAll] = useState(false);
  const [rate, setRate] = useState(lastRate);
  const [silentLine, setSilentLine] = useState<number | null>(null);

  function playLine(i: number, all: boolean) {
    if (!text) return;
    setSilentLine(null);
    player.replace(api.audioSource(text.id, i));
    player.setPlaybackRate(rate, "high");
    player.play();
    setCurrent(i);
    setPlayingAll(all);
    setSession((s) => (s ? heard(s, rate) : s));
  }

  function togglePlay() {
    if (!text) return;
    if (status.playing) player.pause();
    else if (current !== null && !status.didJustFinish && status.currentTime < status.duration) {
      player.setPlaybackRate(rate, "high");
      player.play();
      setSession((s) => (s ? heard(s, rate) : s));
    } else {
      const start = firstLine(text.lines, current === null ? 0 : current + 1) ?? firstLine(text.lines);
      if (start !== null) playLine(start, true);
    }
  }

  function changeRate(next: number) {
    lastRate = next;
    setRate(next);
    player.setPlaybackRate(next, "high");
    if (status.playing) setSession((s) => (s ? heard(s, next) : s));
  }

  useEffect(() => {
    if (!status.didJustFinish || current === null || !text) return;
    const next = nextLine(text.lines, current, playingAll);
    if (next !== null) playLine(next, true);
    else setPlayingAll(false);
    // Reacts to a line ending only.
  }, [status.didJustFinish]);

  // A line whose audio didn't load (the server had none for it): note it and move on.
  useEffect(() => {
    if (!status.error || current === null || !text) return;
    setSilentLine(current);
    const next = nextLine(text.lines, current, playingAll);
    if (next !== null) playLine(next, true);
    else setPlayingAll(false);
    // Reacts to a load error only.
  }, [status.error]);

  async function load() {
    const id = ++loadId.current;
    const stillWanted = () => mounted.current && id === loadId.current;
    player.pause();
    setCurrent(null);
    setPlayingAll(false);
    setSilentLine(null);
    setText(null);
    setError(null);
    setEnded(false);
    setRating(null);
    setWriting(false);
    logged.current = false;
    try {
      const deadline = Date.now() + WRITE_WAIT_MS;
      let next = await api.nextText(topic.id);
      while (next === null) {
        if (!stillWanted()) return;
        setWriting(true);
        if (Date.now() > deadline) {
          throw new ApiError("Writing this text is taking longer than usual. Try again in a minute.", 0);
        }
        await wait(POLL_MS);
        if (!stillWanted()) return;
        next = await api.nextText(topic.id);
      }
      if (!stillWanted()) return;
      setText(next);
      setSession(startSession(next, Date.now()));
    } catch (e) {
      if (stillWanted()) setError(e instanceof ApiError ? e.message : "Couldn't get a text. Try again.");
    }
  }

  useEffect(() => {
    load();
    // Loads once per topic; `load` itself is recreated each render.
  }, [topic.id]);

  // Every way out of a text logs it once, which also takes it off the ready queue.
  async function finish(then: "next" | "back") {
    player.pause();
    if (leaving) {
      // Back while "Next text" is still logging: drop the load that would follow it.
      if (then === "back") {
        loadId.current++;
        onBack();
      }
      return;
    }
    if (text && session && !logged.current) {
      logged.current = true;
      setLeaving(true);
      try {
        await api.logReading(text.id, toLog(session, Date.now(), rating, ended));
      } catch {
        // The reading is lost, not the user's place: carry on either way.
      } finally {
        if (mounted.current) setLeaving(false);
      }
    }
    if (!mounted.current) return;
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
            {writing ? "Writing a text. This takes about half a minute." : "Opening the text"}
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
            <Switch
              value={english}
              onValueChange={setEnglish}
              trackColor={{ true: c.accent }}
              accessibilityLabel="Show English"
            />
          </View>
          {text.lines.map((line, i) => (
            <View
              key={i}
              style={[
                styles.line,
                { borderBottomColor: c.separator },
                current === i && { backgroundColor: c.card, marginHorizontal: 0, paddingHorizontal: spacing.md },
              ]}
            >
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
              {line.audio ? (
                <Pressable
                  onPress={() => playLine(i, false)}
                  accessibilityRole="button"
                  accessibilityLabel={`Play line ${i + 1}`}
                  hitSlop={6}
                  style={[styles.replay, { backgroundColor: c.accentSubtle }]}
                >
                  <Text style={[styles.replayIcon, { color: c.accentText }]}>▶︎</Text>
                </Pressable>
              ) : null}
            </View>
          ))}
          <View style={styles.doneButton}>
            <PrimaryButton
              label="Done"
              onPress={() => {
                player.pause();
                setEnded(true);
              }}
            />
          </View>
        </ScrollView>
      ) : null}

      {text && !ended && firstLine(text.lines) !== null ? (
        <PlayerBar
          playing={status.playing}
          current={current}
          total={text.lines.length}
          rate={rate}
          onToggle={togglePlay}
          onRate={changeRate}
        />
      ) : null}
      {text && !ended && firstLine(text.lines) === null ? (
        <Hint>No audio for this text.</Hint>
      ) : null}
      {text && !ended && silentLine !== null ? (
        <Hint>{`Line ${silentLine + 1} has no audio.`}</Hint>
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
      accessibilityLabel={[word.text, word.stretch && "practice word", flagged && "marked unknown"]
        .filter(Boolean)
        .join(", ")}
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
// Space between the tap and the popover's edge, enough to clear the tapped word.
const POPOVER_GAP = 28;

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
  const insets = useSafeAreaInsets();
  // Measured on first layout (drawn invisible until then), since a long gloss wraps.
  const [popHeight, setPopHeight] = useState(0);
  useEffect(() => setPopHeight(0), [tapped]);
  if (!tapped) return null;
  const left = Math.min(Math.max(tapped.x - 40, spacing.md), width - POPOVER_WIDTH - spacing.md);
  // Above the word when it clears the status bar, so the finger and the word both stay visible;
  // otherwise below it, and never past the bottom edge.
  const above = tapped.y - POPOVER_GAP - popHeight;
  const top = Math.min(
    above >= insets.top + spacing.sm ? above : tapped.y + POPOVER_GAP,
    height - popHeight - insets.bottom - spacing.sm,
  );
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
        onLayout={(e) => setPopHeight(e.nativeEvent.layout.height)}
        style={[
          styles.popover,
          { top, left, opacity: popHeight > 0 ? 1 : 0 },
          { backgroundColor: c.card, borderColor: c.separator, shadowColor: c.shadow },
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

function PlayerBar({
  playing,
  current,
  total,
  rate,
  onToggle,
  onRate,
}: {
  playing: boolean;
  current: number | null;
  total: number;
  rate: number;
  onToggle: () => void;
  onRate: (rate: number) => void;
}) {
  const c = useColors();
  const insets = useSafeAreaInsets();
  return (
    <View
      style={[
        styles.player,
        { backgroundColor: c.card, borderTopColor: c.separator, paddingBottom: insets.bottom + spacing.smd },
      ]}
    >
      <View style={styles.playerRow}>
        <Pressable
          onPress={onToggle}
          accessibilityRole="button"
          accessibilityLabel={playing ? "Pause" : "Play"}
          style={({ pressed }) => [styles.play, { backgroundColor: c.accent, opacity: pressed ? 0.7 : 1 }]}
        >
          <Text style={[styles.playIcon, { color: c.onAccent }]}>{playing ? "❚❚" : "▶︎"}</Text>
        </Pressable>
        <View style={styles.playerText}>
          <Text style={[styles.playerTitle, { color: c.text }]}>
            {current === null ? "Play the dialogue" : `Line ${current + 1} of ${total}`}
          </Text>
          <Text style={[styles.playerHint, { color: c.textSecondary }]}>Tap a line's ▶︎ to replay it</Text>
        </View>
      </View>
      <Segments
        options={RATES.map((r) => ({ value: r, label: `${r.toFixed(1)}×`, accessibilityLabel: `Speed ${r}` }))}
        value={rate}
        onChange={onRate}
      />
    </View>
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
  replay: {
    width: 34,
    height: 34,
    borderRadius: 17,
    alignItems: "center",
    justifyContent: "center",
    marginTop: 6,
  },
  replayIcon: { fontSize: font.md },
  player: {
    borderTopWidth: StyleSheet.hairlineWidth,
    paddingHorizontal: spacing.md,
    paddingTop: spacing.smd,
    gap: spacing.smd,
  },
  playerRow: { flexDirection: "row", alignItems: "center", gap: 14 },
  play: { width: 52, height: 52, borderRadius: 26, alignItems: "center", justifyContent: "center" },
  playIcon: { fontSize: font.xl },
  playerText: { flex: 1 },
  playerTitle: { fontSize: font.md, fontWeight: "600" },
  playerHint: { fontSize: font.sm, marginTop: 2 },
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
