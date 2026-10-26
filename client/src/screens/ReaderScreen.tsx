// The reader: a dialogue split into words by the server, a gloss on tap, audio line by line, and a
// rating at the end.
//
// ==== Layout ====
// NavBar, title, practice words, the Show English and highlight switches, the lines (each with its own replay
// button, and an EN button that shows that line's English alone), then a Done button, with the
// player bar pinned under the scroll view. "Done" swaps the lines for the end view (rating, stats,
// words marked unknown). The gloss popover is a transparent Modal, so a tap's page coordinates
// place it directly.
//
// ==== Reading again ====
// A past text opens in the same reader with nothing logged: no Done, no rating, and no marking words
// unknown, since a second reading of a text isn't recorded. One rated "About right" can be played
// with the text hidden straight away.
//
// ==== Listen only ====
// Once a text is rated "About right", the end view offers to play it again with the text hidden
// (docs/brief.md, design principle 6). The lines show who's speaking instead, the dialogue plays from
// the start, and "Show the text" brings the words back. The reading is logged as listen-only.
//
// ==== Audio ====
// One expo-audio player is reused for every line. "Play" runs the dialogue from the current line to
// the end (`nextLine` in playback.ts); a line's replay button plays that line alone. Speed is the
// player's rate, with pitch kept, so each line is one file whatever the speed. The audio session
// stays active between lines (`keepAudioSessionActive`): expo-audio otherwise drops it after each
// line, and with the screen locked iOS can suspend the app before the next line starts. A line that
// fails to load counts as finished, so "Play" moves on instead of stalling. Whenever the playing
// line changes, the text scrolls to it if it's out of view (`scrollTarget` in follow.ts).
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

import {
  type Api,
  ApiError,
  type PastText,
  type Rating,
  type ReaderText,
  type TextGrammar,
  type Topic,
  type Word,
} from "../api";
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
import { countOutsideDeck, isOutsideDeck, underFloor } from "../deckWords";
import { type Box, scrollTarget } from "../follow";
import { firstLine, nextLine } from "../playback";
import { RATES } from "../playbackRate";
import { prefs, savePrefs } from "../savedPrefs";
import {
  formatDuration,
  heard,
  isFlagged,
  listenedOnly,
  lookUp,
  type Session,
  startSession,
  toLog,
  toggleFlag,
} from "../session";
import { LANGUAGES, wordStatus } from "../languages";
import { type Colors, font, radius, spacing, useColors } from "../theme";

type Tapped = { word: Word; x: number; y: number };

const POLL_MS = 3_000;
// Three attempts and the audio rarely take more than two minutes; past this, something is wrong.
const WRITE_WAIT_MS = 4 * 60_000;

const wait = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));

// A new text on a topic, or a past text to read again.
export type ReaderSource = { kind: "topic"; topic: Topic } | { kind: "past"; text: PastText };

export function ReaderScreen({ api, source, onBack }: { api: Api; source: ReaderSource; onBack: () => void }) {
  const review = source.kind === "past";
  const c = useColors();
  const [text, setText] = useState<ReaderText | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [session, setSession] = useState<Session | null>(null);
  const [english, setEnglish] = useState(false);
  // Lines whose English was shown on their own, while Show English is off.
  const [lineEnglish, setLineEnglish] = useState<number[]>([]);
  const [listenOnly, setListenOnly] = useState(false);
  const [highlight, setHighlight] = useState(prefs().highlight);
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
  const [rate, setRate] = useState(prefs().rate);
  const [silentLine, setSilentLine] = useState<number | null>(null);
  const [repeat, setRepeat] = useState(false);

  const scroller = useRef<ScrollView>(null);
  const lineBoxes = useRef<Box[]>([]);
  const scrollY = useRef(0);
  const viewHeight = useRef(0);

  useEffect(() => {
    const box = current === null ? undefined : lineBoxes.current[current];
    if (!box || !viewHeight.current) return;
    const y = scrollTarget(box, scrollY.current, viewHeight.current);
    if (y !== null) scroller.current?.scrollTo({ y, animated: true });
  }, [current]);

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
    savePrefs({ rate: next });
    setRate(next);
    player.setPlaybackRate(next, "high");
    if (status.playing) setSession((s) => (s ? heard(s, next) : s));
  }

  useEffect(() => {
    if (!status.didJustFinish || current === null || !text) return;
    const next = nextLine(text.lines, current, playingAll, repeat);
    if (next === current) {
      // The same source again: rewind rather than reload it.
      player.seekTo(0).then(() => player.play(), () => {});
      return;
    }
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
    setLineEnglish([]);
    setListenOnly(false);
    lineBoxes.current = [];
    scrollY.current = 0;
    logged.current = false;
    try {
      if (source.kind === "past") {
        const past = await api.text(source.text.id);
        if (!stillWanted()) return;
        setText(past);
        setSession(startSession(past, Date.now()));
        return;
      }
      const topicId = source.topic.id;
      const deadline = Date.now() + WRITE_WAIT_MS;
      let next = await api.nextText(topicId);
      while (next === null) {
        if (!stillWanted()) return;
        setWriting(true);
        if (Date.now() > deadline) {
          throw new ApiError("Writing this text is taking longer than usual. Try again in a minute.", 0);
        }
        await wait(POLL_MS);
        if (!stillWanted()) return;
        next = await api.nextText(topicId);
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
    // Loads once per source; `load` itself is recreated each render.
  }, [source]);

  // Finishing a text (Done) logs it once, which also takes it off the ready queue. Backing out
  // before Done logs nothing, so the same text is waiting next time instead of a new one.
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
    // A listen-only pass is only offered after Done, so it counts as finished too. Reading a
    // past text again is never logged.
    const finished = ended || (session?.listenOnly ?? false);
    if (text && session && finished && !review && !logged.current) {
      logged.current = true;
      setLeaving(true);
      try {
        await api.logReading(text.id, toLog(session, Date.now(), rating, true));
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

  function toggleLineEnglish(i: number) {
    setLineEnglish((shown) => (shown.includes(i) ? shown.filter((n) => n !== i) : [...shown, i]));
  }

  function listenWithoutText() {
    if (!text) return;
    setSession((s) => (s ? listenedOnly(s) : s));
    setListenOnly(true);
    setEnded(false);
    scrollY.current = 0; // the lines' scroll view is mounted fresh
    const start = firstLine(text.lines);
    if (start !== null) playLine(start, true);
  }

  const seconds = session ? Math.round((Date.now() - session.startedAt) / 1000) : 0;

  return (
    <View style={styles.root}>
      <NavBar
        back={review ? "Past texts" : "Topics"}
        title={source.kind === "topic" ? source.topic.name : source.text.topic}
        onBack={() => finish("back")}
      />
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
        <ScrollView
          ref={scroller}
          contentContainerStyle={styles.content}
          onLayout={(e) => (viewHeight.current = e.nativeEvent.layout.height)}
          onScroll={(e) => (scrollY.current = e.nativeEvent.contentOffset.y)}
          scrollEventThrottle={100}
        >
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
          {practicedGrammar(text).length > 0 ? (
            <View style={styles.practice}>
              <Text style={[styles.practiceLabel, { color: c.textSecondary }]}>Grammar:</Text>
              {practicedGrammar(text).map((g) => (
                <Text key={g.id} style={[styles.chip, { backgroundColor: c.speakerB, color: c.speakerBText }]}>
                  {g.name}
                </Text>
              ))}
            </View>
          ) : null}
          {text.roles.A || text.roles.B ? (
            <View style={styles.roles}>
              {(["A", "B"] as const).map((who) =>
                text.roles[who] ? (
                  <View key={who} style={styles.role}>
                    <Text style={[styles.roleBadge, speakerColors(c, who)]}>{who}</Text>
                    <Text style={[styles.roleName, { color: c.textSecondary }]}>{text.roles[who]}</Text>
                  </View>
                ) : null,
              )}
            </View>
          ) : null}
          {review && !listenOnly && source.text.rating === "about_right" && firstLine(text.lines) !== null ? (
            <View style={styles.listenOnly}>
              <Text style={[styles.toggleText, { color: c.textSecondary }]}>You rated this about right</Text>
              <PillButton label="Listen without the text" quiet onPress={listenWithoutText} />
            </View>
          ) : null}
          {listenOnly ? (
            <View style={styles.listenOnly}>
              <Text style={[styles.toggleText, { color: c.textSecondary }]}>Listening without the text</Text>
              <PillButton label="Show the text" quiet onPress={() => setListenOnly(false)} />
            </View>
          ) : (
            <>
              <View style={styles.toggle}>
                <Text style={[styles.toggleText, { color: c.textSecondary }]}>Show English</Text>
                <Switch
                  value={english}
                  onValueChange={setEnglish}
                  trackColor={{ true: c.accent }}
                  accessibilityLabel="Show English"
                />
              </View>
              <View style={[styles.toggle, styles.toggleNext]}>
                <Text style={[styles.toggleText, { color: c.textSecondary }]}>
                  {LANGUAGES[text.language ?? "th"].highlightLabel}
                </Text>
                <Switch
                  value={highlight}
                  onValueChange={(on) => {
                    savePrefs({ highlight: on });
                    setHighlight(on);
                  }}
                  trackColor={{ true: c.accent }}
                  accessibilityLabel={LANGUAGES[text.language ?? "th"].highlightLabel}
                />
              </View>
              {highlight && countOutsideDeck(text) === 0 ? (
                <Text style={[styles.toggleNote, { color: c.textTertiary }]}>
                  Every word in this text is in your deck.
                </Text>
              ) : null}
              {underFloor(text) ? (
                <View style={[styles.underFloor, { backgroundColor: c.card }]}>
                  <Text style={[styles.underFloorText, { color: c.textSecondary }]}>
                    {`${Math.round(text.coverage * 100)}% of the words in this one are in your deck, fewer than usual. Tap any word for its meaning.`}
                  </Text>
                  {highlight ? null : (
                    <PillButton
                      label="Highlight them"
                      quiet
                      onPress={() => {
                        savePrefs({ highlight: true });
                        setHighlight(true);
                      }}
                    />
                  )}
                </View>
              ) : null}
            </>
          )}
          {text.lines.map((line, i) => (
            <View
              key={i}
              onLayout={(e) => {
                const { y, height } = e.nativeEvent.layout;
                lineBoxes.current[i] = { y, height };
              }}
              style={[
                styles.line,
                { borderBottomColor: c.separator },
                current === i && { backgroundColor: c.card, marginHorizontal: 0, paddingHorizontal: spacing.md },
              ]}
            >
              {line.speaker === "N" ? null : (
                <Text style={[styles.speaker, speakerColors(c, line.speaker)]}>{line.speaker}</Text>
              )}
              <View style={styles.lineBody}>
                {listenOnly ? (
                  <Text style={[styles.hiddenLine, { color: c.textTertiary }]}>
                    {(line.speaker !== "N" && text.roles[line.speaker]) || `Line ${i + 1}`}
                  </Text>
                ) : (
                  <View style={styles.words}>
                    {line.words.map((word, j) => (
                      <WordView
                        key={j}
                        word={word}
                        textStyle={readStyle(text)}
                        grammar={grammarOf(text, word)}
                        flagged={isFlagged(session, word.text)}
                        highlighted={highlight && isOutsideDeck(word)}
                        selected={tapped?.word === word}
                        onPress={tap}
                      />
                    ))}
                  </View>
                )}
                {!listenOnly && (english || lineEnglish.includes(i)) ? (
                  <Text style={[styles.english, { color: c.textSecondary }]}>{line.english}</Text>
                ) : null}
              </View>
              <View style={styles.lineButtons}>
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
                {!english && !listenOnly ? (
                  <Pressable
                    onPress={() => toggleLineEnglish(i)}
                    accessibilityRole="button"
                    accessibilityLabel={
                      lineEnglish.includes(i) ? `Hide English for line ${i + 1}` : `Show English for line ${i + 1}`
                    }
                    hitSlop={6}
                    style={[
                      styles.replay,
                      { backgroundColor: lineEnglish.includes(i) ? c.accentSubtle : c.tertiary },
                    ]}
                  >
                    <Text
                      style={[styles.enLabel, { color: lineEnglish.includes(i) ? c.accentText : c.textSecondary }]}
                    >
                      EN
                    </Text>
                  </Pressable>
                ) : null}
              </View>
            </View>
          ))}
          {review ? null : (
            <View style={styles.doneButton}>
              <PrimaryButton
                label="Done"
                onPress={() => {
                  player.pause();
                  setEnded(true);
                }}
              />
            </View>
          )}
        </ScrollView>
      ) : null}

      {text && !ended && firstLine(text.lines) !== null ? (
        <PlayerBar
          playing={status.playing}
          current={current}
          total={text.lines.length}
          what={text.form === "story" ? "story" : "dialogue"}
          rate={rate}
          repeat={repeat}
          onToggle={togglePlay}
          onRate={changeRate}
          onRepeat={() => setRepeat((r) => !r)}
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
          {rating === "about_right" && firstLine(text.lines) !== null ? (
            <View style={styles.listenAgain}>
              <PillButton label="Listen without the text" onPress={listenWithoutText} />
              <Hint>Plays it again with the text hidden.</Hint>
            </View>
          ) : null}
          <View style={styles.endButtons}>
            <PrimaryButton label="Next text" onPress={() => finish("next")} busy={leaving} />
            <TextButton label="Back to topics" onPress={() => finish("back")} />
          </View>
        </ScrollView>
      ) : null}

      <GlossPopover
        tapped={tapped}
        grammar={tapped && text ? grammarOf(text, tapped.word) : null}
        flagged={tapped && session ? isFlagged(session, tapped.word.text) : false}
        onToggleFlag={
          review ? null : () => tapped && session && setSession(toggleFlag(session, tapped.word.text))
        }
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

// The reading size for a text's language. `language` is missing from a server older than Spanish.
function readStyle(text: ReaderText) {
  const info = LANGUAGES[text.language ?? "th"];
  return { fontSize: info.fontSize, lineHeight: info.fontSize * info.lineHeight };
}

// `grammar` is missing from a server older than grammar choices.
function practicedGrammar(text: ReaderText): TextGrammar[] {
  return (text.grammar ?? []).filter((g) => g.role === "practice");
}

function grammarOf(text: ReaderText, word: Word): TextGrammar | null {
  return word.grammar ? ((text.grammar ?? []).find((g) => g.id === word.grammar) ?? null) : null;
}

function speakerColors(c: Colors, who: "A" | "B") {
  return who === "A"
    ? { backgroundColor: c.accentSubtle, color: c.accentText }
    : { backgroundColor: c.speakerB, color: c.speakerBText };
}

function glossFor(text: ReaderText, word: string): string | null {
  for (const line of text.lines) for (const w of line.words) if (w.text === word && w.gloss) return w.gloss;
  return null;
}

function WordView({
  word,
  grammar,
  textStyle,
  flagged,
  highlighted,
  selected,
  onPress,
}: {
  word: Word;
  grammar: TextGrammar | null;
  textStyle: { fontSize: number; lineHeight: number };
  flagged: boolean;
  highlighted: boolean;
  selected: boolean;
  onPress: (word: Word, x: number, y: number) => void;
}) {
  const c = useColors();
  if (word.status === null) {
    // A space becomes a gap; punctuation is shown but can't be tapped.
    return word.text.trim() ? (
      <Text style={[textStyle, { color: c.text }]}>{word.text}</Text>
    ) : (
      <View style={{ width: textStyle.fontSize * 0.3 }} />
    );
  }
  return (
    <Pressable
      onPress={(e) => onPress(word, e.nativeEvent.pageX, e.nativeEvent.pageY)}
      accessibilityRole="button"
      accessibilityLabel={[
        word.text,
        word.stretch && "practice word",
        grammar && grammar.name,
        highlighted && "not in your deck",
        flagged && "marked unknown",
      ]
        .filter(Boolean)
        .join(", ")}
      accessibilityHint="Shows what this word means"
      style={[
        styles.word,
        highlighted && { backgroundColor: c.outsideDeck },
        selected && { backgroundColor: c.accentSubtle, borderColor: c.accent },
      ]}
    >
      <Text
        style={[
          textStyle,
          { color: word.stretch ? c.accentText : c.text },
          word.stretch && styles.stretch,
          // Grammar is underlined solid when practiced, dashed when it slipped in while avoided;
          // a practice word's or a marked word's dotted underline takes its place.
          grammar && {
            textDecorationLine: "underline",
            textDecorationStyle: grammar.role === "practice" ? "solid" : "dashed",
            textDecorationColor: grammar.role === "practice" ? c.speakerBText : c.textTertiary,
          },
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
  grammar,
  flagged,
  onToggleFlag,
  onClose,
}: {
  tapped: Tapped | null;
  grammar: TextGrammar | null;
  flagged: boolean;
  onToggleFlag: (() => void) | null; // null when marking isn't recorded (reading a past text)
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
  const status = wordStatus(tapped.word);
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
        {grammar ? (
          <Text style={[styles.popGrammar, { color: c.textSecondary }]}>
            {grammar.role === "practice"
              ? `Grammar you're practicing: ${grammar.name}. ${grammar.note}.`
              : `${grammar.name}, which you're avoiding, slipped in here. ${grammar.note}.`}
          </Text>
        ) : null}
        {onToggleFlag ? (
          <View style={styles.popActions}>
            <PillButton label={flagged ? "Unmark" : "Mark as unknown"} onPress={onToggleFlag} />
          </View>
        ) : null}
      </View>
    </Modal>
  );
}

function PlayerBar({
  playing,
  current,
  total,
  what,
  rate,
  repeat,
  onToggle,
  onRate,
  onRepeat,
}: {
  playing: boolean;
  current: number | null;
  total: number;
  what: "dialogue" | "story";
  rate: number;
  repeat: boolean;
  onToggle: () => void;
  onRate: (rate: number) => void;
  onRepeat: () => void;
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
            {current === null ? `Play the ${what}` : `Line ${current + 1} of ${total}`}
          </Text>
          <Text style={[styles.playerHint, { color: c.textSecondary }]}>
            {repeat ? "Repeating this line" : "Tap a line's ▶︎ to replay it"}
          </Text>
        </View>
        <Pressable
          onPress={onRepeat}
          accessibilityRole="switch"
          accessibilityLabel="Repeat line"
          accessibilityState={{ checked: repeat }}
          style={({ pressed }) => [
            styles.repeat,
            { backgroundColor: repeat ? c.accentSubtle : c.tertiary, opacity: pressed ? 0.7 : 1 },
          ]}
        >
          <Text style={[styles.repeatText, { color: repeat ? c.accentText : c.textSecondary }]}>Repeat line</Text>
        </Pressable>
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
  toggleText: { fontSize: font.md, flexShrink: 1 },
  toggleNext: { paddingTop: 0 },
  underFloor: {
    flexDirection: "row",
    alignItems: "center",
    gap: spacing.smd,
    marginHorizontal: spacing.md,
    marginBottom: spacing.sm,
    padding: spacing.smd,
    borderRadius: radius.md,
  },
  underFloorText: { flex: 1, fontSize: font.sm, lineHeight: 18 },
  toggleNote: { fontSize: font.sm, paddingHorizontal: spacing.md, paddingBottom: spacing.sm },
  line: {
    flexDirection: "row",
    gap: 10,
    marginHorizontal: spacing.md,
    paddingVertical: spacing.smd,
    borderBottomWidth: StyleSheet.hairlineWidth,
  },
  roles: { flexDirection: "row", flexWrap: "wrap", gap: spacing.md, paddingHorizontal: spacing.md, paddingTop: spacing.sm },
  role: { flexDirection: "row", alignItems: "center", gap: 6 },
  roleBadge: {
    width: 22,
    height: 22,
    borderRadius: 11,
    overflow: "hidden",
    textAlign: "center",
    lineHeight: 22,
    fontSize: font.sm,
    fontWeight: "700",
  },
  roleName: { fontSize: font.md },
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
    // Thai has no spaces between words. The negative margin cancels the border
    // so tappable words sit flush and only real spaces in the text show as gaps.
    marginHorizontal: -1.5,
  },
  stretch: { fontWeight: "700" },
  english: { fontSize: 14, lineHeight: 18, marginTop: 2 },
  hiddenLine: { fontSize: font.md, lineHeight: 40 },
  lineButtons: { gap: spacing.xs },
  enLabel: { fontSize: font.xs, fontWeight: "700" },
  listenOnly: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "center",
    paddingHorizontal: spacing.md,
    paddingTop: spacing.md,
    paddingBottom: spacing.sm,
  },
  listenAgain: { alignItems: "center", paddingTop: spacing.sm },
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
  repeat: { borderRadius: radius.full, paddingHorizontal: spacing.smd, paddingVertical: spacing.sm },
  repeatText: { fontSize: font.sm, fontWeight: "600" },
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
  popGrammar: { fontSize: font.sm, marginTop: 6, lineHeight: 18 },
  popStatus: { fontSize: font.sm, marginTop: 6 },
  popActions: { flexDirection: "row", gap: spacing.sm, marginTop: 14 },
});
