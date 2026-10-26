// Four screens and no navigation library: login, topics, the reader for one topic, and the words
// marked unknown.
import { setAudioModeAsync } from "expo-audio";
import { StatusBar } from "expo-status-bar";
import { useEffect, useMemo, useState } from "react";
import { ActivityIndicator, StyleSheet, View } from "react-native";
import { SafeAreaProvider, SafeAreaView } from "react-native-safe-area-context";

import { createApi, type Topic } from "./src/api";
import { clearPassphrase, loadPassphrase, serverUrl } from "./src/passphrase";
import { loadPrefs } from "./src/savedPrefs";
import { LoginScreen } from "./src/screens/LoginScreen";
import { ReaderScreen } from "./src/screens/ReaderScreen";
import { TopicsScreen } from "./src/screens/TopicsScreen";
import { WordsScreen } from "./src/screens/WordsScreen";
import { useColors } from "./src/theme";

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
  const [topic, setTopic] = useState<Topic | null>(null);
  const [words, setWords] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const url = serverUrl();

  function logOut(reason: string | null) {
    clearPassphrase().catch(() => {});
    setTopic(null);
    setWords(false);
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
  else if (topic) screen = <ReaderScreen api={api} topic={topic} onBack={() => setTopic(null)} />;
  else if (words) screen = <WordsScreen api={api} onBack={() => setWords(false)} />;
  else
    screen = (
      <TopicsScreen api={api} onOpen={setTopic} onWords={() => setWords(true)} onLogOut={() => logOut(null)} />
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
