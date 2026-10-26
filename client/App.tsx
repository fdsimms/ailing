// Screens switched by state, with no navigation library: login, topics, the reader (a new text on a
// topic, or a past text again), past texts, and the words marked unknown.
import { setAudioModeAsync } from "expo-audio";
import { StatusBar } from "expo-status-bar";
import { useEffect, useMemo, useState } from "react";
import { ActivityIndicator, StyleSheet, View } from "react-native";
import { SafeAreaProvider, SafeAreaView } from "react-native-safe-area-context";

import { createApi } from "./src/api";
import { clearPassphrase, loadPassphrase, serverUrl } from "./src/passphrase";
import { loadPrefs } from "./src/savedPrefs";
import { LoginScreen } from "./src/screens/LoginScreen";
import { GrammarScreen } from "./src/screens/GrammarScreen";
import { PastTextsScreen } from "./src/screens/PastTextsScreen";
import { ReaderScreen, type ReaderSource } from "./src/screens/ReaderScreen";
import { TopicsScreen } from "./src/screens/TopicsScreen";
import { WordsScreen } from "./src/screens/WordsScreen";
import { useColors } from "./src/theme";

type Route =
  | { kind: "topics" }
  | { kind: "words" }
  | { kind: "past" }
  | { kind: "grammar" }
  | { kind: "reader"; source: ReaderSource };

export default function App() {
  return (
    <SafeAreaProvider>
      <Root />
    </SafeAreaProvider>
  );
}

function Root() {
  const c = useColors();
  const [passphrase, setPassphrase] = useState<string | null | undefined>(undefined);
  const [view, setView] = useState<Route>({ kind: "topics" });
  const [notice, setNotice] = useState<string | null>(null);
  const url = serverUrl();

  function logOut(reason: string | null) {
    clearPassphrase().catch(() => {});
    setView({ kind: "topics" });
    setNotice(reason);
    setPassphrase(null);
  }

  useEffect(() => {
    // The reader's saved speed and highlight are read before anything shows, so it opens with them.
    Promise.all([loadPassphrase(), loadPrefs()]).then(
      ([saved]) => setPassphrase(saved),
      () => setPassphrase(null),
    );
    // Keeps playing with the ringer switch on silent, and with the screen locked.
    setAudioModeAsync({ playsInSilentMode: true, shouldPlayInBackground: true }).catch(() => {});
  }, []);

  const api = useMemo(
    () =>
      url && passphrase
        ? createApi(url, passphrase, fetch, () =>
            logOut("The passphrase changed on the server. Enter the new one."),
          )
        : null,
    [url, passphrase],
  );

  let screen;
  if (passphrase === undefined) screen = <ActivityIndicator style={styles.loading} />;
  else if (!api) screen = <LoginScreen notice={notice} onLoggedIn={setPassphrase} />;
  else if (view.kind === "reader") {
    const source = view.source;
    const back = () => setView({ kind: source.kind === "past" ? "past" : "topics" });
    screen = <ReaderScreen api={api} source={source} onBack={back} />;
  } else if (view.kind === "words") screen = <WordsScreen api={api} onBack={() => setView({ kind: "topics" })} />;
  else if (view.kind === "grammar") screen = <GrammarScreen api={api} onBack={() => setView({ kind: "topics" })} />;
  else if (view.kind === "past")
    screen = (
      <PastTextsScreen
        api={api}
        onOpen={(text) => setView({ kind: "reader", source: { kind: "past", text } })}
        onBack={() => setView({ kind: "topics" })}
      />
    );
  else
    screen = (
      <TopicsScreen
        api={api}
        onOpen={(topic) => setView({ kind: "reader", source: { kind: "topic", topic } })}
        onWords={() => setView({ kind: "words" })}
        onPast={() => setView({ kind: "past" })}
        onGrammar={() => setView({ kind: "grammar" })}
        onLogOut={() => logOut(null)}
      />
    );

  return (
    <SafeAreaView style={[styles.root, { backgroundColor: c.bg }]} edges={["top", "left", "right"]}>
      <View style={styles.root}>{screen}</View>
      <StatusBar style="auto" />
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1 },
  loading: { marginTop: 64 },
});
