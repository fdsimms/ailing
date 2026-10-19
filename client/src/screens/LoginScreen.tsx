import { useState } from "react";
import { StyleSheet, Text, TextInput, View } from "react-native";

import { ApiError, createApi } from "../api";
import { ErrorNote, PrimaryButton } from "../components/ui";
import { savePassphrase, serverUrl } from "../passphrase";
import { font, radius, spacing, useColors } from "../theme";

export function LoginScreen({ onLoggedIn }: { onLoggedIn: (passphrase: string) => void }) {
  const c = useColors();
  const [value, setValue] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const url = serverUrl();

  async function logIn() {
    if (!url) return;
    setBusy(true);
    setError(null);
    try {
      await createApi(url, value.trim()).check();
      await savePassphrase(value.trim());
      onLoggedIn(value.trim());
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Couldn't log in. Try again.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <View style={styles.root}>
      <Text style={[styles.title, { color: c.text }]}>Read &amp; Listen</Text>
      <Text style={[styles.sub, { color: c.textSecondary }]}>
        Enter the passphrase set on the server. You only need to do this once.
      </Text>
      {url ? (
        <>
          <TextInput
            style={[styles.input, { backgroundColor: c.card, color: c.text }]}
            placeholder="Passphrase"
            placeholderTextColor={c.textTertiary}
            secureTextEntry
            autoCapitalize="none"
            autoCorrect={false}
            onChangeText={setValue}
            onSubmitEditing={logIn}
            returnKeyType="go"
          />
          <PrimaryButton label="Log in" onPress={logIn} busy={busy} disabled={!value.trim()} />
          {error ? <ErrorNote message={error} /> : null}
        </>
      ) : (
        <ErrorNote message="This build has no server address. Rebuild it with EXPO_PUBLIC_API_URL set." />
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, padding: spacing.md, paddingTop: spacing.xl, gap: spacing.md },
  title: { fontSize: font.title, fontWeight: "700" },
  sub: { fontSize: font.md, lineHeight: 21 },
  input: { minHeight: 50, borderRadius: radius.md, paddingHorizontal: spacing.md, fontSize: font.lg },
});
