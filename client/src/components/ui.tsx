// The handful of shared pieces the three screens are built from.
import type { ReactNode } from "react";
import {
  ActivityIndicator,
  Pressable,
  type StyleProp,
  StyleSheet,
  Text,
  View,
  type ViewStyle,
} from "react-native";

import { font, radius, spacing, useColors } from "../theme";

export function NavBar({ back, title, onBack }: { back?: string; title?: string; onBack?: () => void }) {
  const c = useColors();
  return (
    <View style={styles.nav}>
      <Pressable onPress={onBack} hitSlop={12} accessibilityRole="button" style={styles.navSide}>
        {back ? <Text style={[styles.back, { color: c.accentText }]}>‹ {back}</Text> : null}
      </Pressable>
      <Text style={[styles.navTitle, { color: c.text }]} numberOfLines={1}>
        {title}
      </Text>
      <View style={styles.navSide} />
    </View>
  );
}

export function SectionLabel({ children }: { children: string }) {
  const c = useColors();
  return <Text style={[styles.section, { color: c.textSecondary }]}>{children.toUpperCase()}</Text>;
}

export function Card({ children }: { children: ReactNode }) {
  const c = useColors();
  return <View style={[styles.card, { backgroundColor: c.card }]}>{children}</View>;
}

export function Hint({ children }: { children: string }) {
  const c = useColors();
  return <Text style={[styles.hint, { color: c.textTertiary }]}>{children}</Text>;
}

// A row of equal segments, one of them chosen: the reader's speed, the stretch words setting.
export function Segments<T extends string | number>({
  options,
  value,
  onChange,
  style,
}: {
  options: { value: T; label: string; accessibilityLabel?: string }[];
  value: T;
  onChange: (value: T) => void;
  style?: StyleProp<ViewStyle>;
}) {
  const c = useColors();
  return (
    <View style={[styles.segments, { backgroundColor: c.tertiary }, style]} accessibilityRole="radiogroup">
      {options.map((o) => (
        <Pressable
          key={o.value}
          onPress={() => onChange(o.value)}
          accessibilityRole="radio"
          accessibilityState={{ selected: o.value === value }}
          accessibilityLabel={o.accessibilityLabel ?? o.label}
          style={[styles.segment, o.value === value && { backgroundColor: c.card }]}
        >
          <Text style={[styles.segmentText, { color: o.value === value ? c.text : c.textSecondary }]}>
            {o.label}
          </Text>
        </Pressable>
      ))}
    </View>
  );
}

export function PrimaryButton({
  label,
  onPress,
  busy,
  disabled,
}: {
  label: string;
  onPress: () => void;
  busy?: boolean;
  disabled?: boolean;
}) {
  const c = useColors();
  return (
    <Pressable
      onPress={onPress}
      disabled={disabled || busy}
      accessibilityRole="button"
      style={({ pressed }) => [
        styles.primary,
        { backgroundColor: c.accent, opacity: disabled ? 0.5 : pressed ? 0.7 : 1 },
      ]}
    >
      {busy ? (
        <ActivityIndicator color={c.onAccent} />
      ) : (
        <Text style={[styles.primaryText, { color: c.onAccent }]}>{label}</Text>
      )}
    </Pressable>
  );
}

export function TextButton({ label, onPress }: { label: string; onPress: () => void }) {
  const c = useColors();
  return (
    <Pressable onPress={onPress} accessibilityRole="button" hitSlop={8} style={styles.textButton}>
      <Text style={[styles.textButtonText, { color: c.accentText }]}>{label}</Text>
    </Pressable>
  );
}

export function PillButton({
  label,
  onPress,
  quiet,
}: {
  label: string;
  onPress: () => void;
  quiet?: boolean;
}) {
  const c = useColors();
  return (
    <Pressable
      onPress={onPress}
      accessibilityRole="button"
      style={({ pressed }) => [
        styles.pill,
        { backgroundColor: quiet ? c.tertiary : c.accentSubtle, opacity: pressed ? 0.7 : 1 },
      ]}
    >
      <Text style={[styles.pillText, { color: quiet ? c.text : c.accentText }]}>{label}</Text>
    </Pressable>
  );
}

export function ErrorNote({ message, onRetry }: { message: string; onRetry?: () => void }) {
  const c = useColors();
  return (
    <View style={styles.error}>
      <Text style={[styles.errorText, { color: c.textSecondary }]}>{message}</Text>
      {onRetry ? <TextButton label="Try again" onPress={onRetry} /> : null}
    </View>
  );
}

const styles = StyleSheet.create({
  segments: { flexDirection: "row", borderRadius: 9, padding: 2 },
  segment: { flex: 1, alignItems: "center", paddingVertical: 6, borderRadius: 7 },
  segmentText: { fontSize: font.sm, fontWeight: "600" },
  nav: { minHeight: 44, flexDirection: "row", alignItems: "center", paddingHorizontal: spacing.md },
  navSide: { width: 96 },
  back: { fontSize: font.lg },
  navTitle: { flex: 1, textAlign: "center", fontSize: font.lg, fontWeight: "600" },
  section: {
    fontSize: font.xs,
    fontWeight: "600",
    letterSpacing: 0.8,
    paddingHorizontal: spacing.xl,
    paddingTop: spacing.lg,
    paddingBottom: spacing.sm,
  },
  card: { borderRadius: radius.md, marginHorizontal: spacing.md, overflow: "hidden" },
  hint: { fontSize: font.sm, lineHeight: 18, paddingHorizontal: spacing.xl, paddingTop: spacing.sm },
  primary: {
    minHeight: 50,
    borderRadius: radius.md,
    alignItems: "center",
    justifyContent: "center",
    paddingHorizontal: spacing.md,
  },
  primaryText: { fontSize: font.lg, fontWeight: "600" },
  textButton: { alignItems: "center", paddingVertical: spacing.smd },
  textButtonText: { fontSize: font.lg },
  pill: { borderRadius: radius.full, paddingHorizontal: spacing.smd, paddingVertical: spacing.sm },
  pillText: { fontSize: font.md, fontWeight: "600" },
  error: { padding: spacing.lg, alignItems: "center", gap: spacing.sm },
  errorText: { fontSize: font.md, textAlign: "center", lineHeight: 21 },
});
