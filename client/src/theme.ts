// Colors and spacing from dundundun (fdsimms/todo, src/theme/index.ts), so the two apps feel like
// siblings. Light is dundundun's Light, dark is its Dark ("night").
import { useColorScheme } from "react-native";

const INK = "#17131C";
const PAPER = "#F6F3F8";

export const lightColors = {
  bg: "#F3F2F5",
  card: "#FFFFFF",
  tertiary: "#EFEDF3",
  text: INK,
  textSecondary: "#4F4A57",
  textTertiary: "#6B6574",
  accent: "#6A3FDB",
  accentText: "#6032D0",
  accentSubtle: "rgba(106, 63, 219, 0.1)",
  onAccent: "#FFFFFF",
  separator: "#C9C6CF",
  speakerB: "#D2E6DB",
  speakerBText: "#24563F",
  red: "#C4281C",
  // Behind a word that isn't in the deck, when the reader highlights them.
  outsideDeck: "#FBE2B0",
  shadow: "rgba(23, 19, 28, 0.18)",
};

export type Colors = typeof lightColors;

export const darkColors: Colors = {
  bg: "#16121F",
  card: "#1F1A2C",
  tertiary: "#2A2338",
  text: PAPER,
  textSecondary: "#ACA4BA",
  textTertiary: "#9289A3",
  accent: "#9B7BFF",
  accentText: "#B9A0FF",
  accentSubtle: "rgba(155, 123, 255, 0.2)",
  onAccent: INK,
  separator: "#3D3550",
  speakerB: "#22392F",
  speakerBText: "#9FD6BB",
  red: "#FF6961",
  outsideDeck: "#4D3A14",
  shadow: "rgba(0, 0, 0, 0.6)",
};

export const spacing = { xs: 4, sm: 8, smd: 12, md: 16, lg: 24, xl: 32 };
export const radius = { sm: 8, md: 12, lg: 16, full: 9999 };
export const font = { xxs: 11, xs: 12, sm: 13, md: 15, lg: 17, xl: 20, xxl: 28, title: 34 };
// Thai sits bigger than Latin text at the same size, and is the thing being read.
export const thaiFont = 23;

export function useColors(): Colors {
  return useColorScheme() === "dark" ? darkColors : lightColors;
}
