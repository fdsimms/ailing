// The passphrase lives in the iOS keychain (docs/architecture.md, Hosting), never in plain storage.
import * as SecureStore from "expo-secure-store";

const KEY = "passphrase";

export const loadPassphrase = () => SecureStore.getItemAsync(KEY);
export const savePassphrase = (value: string) => SecureStore.setItemAsync(KEY, value);
export const clearPassphrase = () => SecureStore.deleteItemAsync(KEY);

export const serverUrl = (): string | undefined => process.env.EXPO_PUBLIC_API_URL || undefined;
