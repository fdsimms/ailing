// Reader settings kept in the keychain next to the passphrase. Loaded once at launch; a failed save
// only means the setting resets next launch.
import * as SecureStore from "expo-secure-store";

import { DEFAULT_PREFS, parsePrefs, type Prefs } from "./prefs";

const KEY = "prefs";

let current: Prefs = DEFAULT_PREFS;

export async function loadPrefs(): Promise<void> {
  try {
    current = parsePrefs(await SecureStore.getItemAsync(KEY));
  } catch {
    current = DEFAULT_PREFS;
  }
}

export const prefs = (): Prefs => current;

export function savePrefs(change: Partial<Prefs>): void {
  current = { ...current, ...change };
  SecureStore.setItemAsync(KEY, JSON.stringify(current)).catch(() => {});
}
