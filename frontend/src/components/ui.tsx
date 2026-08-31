import React from "react";
import {
  View,
  Text,
  Pressable,
  StyleSheet,
  TextInput,
  ActivityIndicator,
  ViewStyle,
  TextStyle,
  StyleProp,
} from "react-native";
import { Ionicons } from "@expo/vector-icons";
import * as Haptics from "expo-haptics";
import { useTheme } from "@/src/theme/ThemeProvider";

export function Card({
  children,
  style,
  onPress,
  testID,
}: {
  children: React.ReactNode;
  style?: StyleProp<ViewStyle>;
  onPress?: () => void;
  testID?: string;
}) {
  const { colors, radius, spacing } = useTheme();
  const base: ViewStyle = {
    backgroundColor: colors.surfaceSecondary,
    borderRadius: radius.lg,
    padding: spacing.lg,
    borderWidth: 1,
    borderColor: colors.border,
  };
  if (onPress) {
    return (
      <Pressable
        testID={testID}
        onPress={onPress}
        style={({ pressed }) => [base, style, pressed && { opacity: 0.7 }]}
      >
        {children}
      </Pressable>
    );
  }
  return (
    <View testID={testID} style={[base, style]}>
      {children}
    </View>
  );
}

export function AppText({
  children,
  variant = "body",
  color,
  style,
  numberOfLines,
  testID,
}: {
  children: React.ReactNode;
  variant?: "display" | "title" | "heading" | "body" | "label" | "caption" | "mono";
  color?: string;
  style?: StyleProp<TextStyle>;
  numberOfLines?: number;
  testID?: string;
}) {
  const { colors, fonts, fontSize } = useTheme();
  // No fontFamily here: the weight decides the face, and callers routinely
  // override the weight through `style`, so the family is resolved below from
  // whatever weight actually survives the cascade.
  const map: Record<string, TextStyle> = {
    display: { fontSize: fontSize["4xl"], fontWeight: "700", color: colors.onSurface, letterSpacing: -0.5 },
    title: { fontSize: fontSize["2xl"], fontWeight: "700", color: colors.onSurface },
    heading: { fontSize: fontSize.xl, fontWeight: "600", color: colors.onSurface },
    body: { fontSize: fontSize.lg, color: colors.onSurface },
    label: { fontSize: fontSize.base, fontWeight: "600", color: colors.onSurfaceTertiary },
    caption: { fontSize: fontSize.sm, color: colors.onSurfaceTertiary },
    mono: { fontSize: fontSize["3xl"], fontWeight: "700", color: colors.onSurface, letterSpacing: -0.5 },
  };
  const { fontWeight, ...rest } = StyleSheet.flatten([map[variant], color ? { color } : null, style]) as TextStyle;
  const role = variant === "display" || variant === "mono" ? "display" : "text";
  // fontWeight is pulled out rather than overridden: face() either hands back
  // the face that carries that weight, or the weight itself as the fallback.
  return (
    <Text testID={testID} numberOfLines={numberOfLines} style={[rest, fonts.face(role, fontWeight)]}>
      {children}
    </Text>
  );
}

export function PrimaryButton({
  title,
  onPress,
  loading,
  disabled,
  icon,
  variant = "primary",
  testID,
  style,
}: {
  title: string;
  onPress: () => void;
  loading?: boolean;
  disabled?: boolean;
  icon?: keyof typeof Ionicons.glyphMap;
  variant?: "primary" | "secondary" | "outline";
  testID?: string;
  style?: StyleProp<ViewStyle>;
}) {
  const { colors, radius, spacing, fonts } = useTheme();
  const bg =
    variant === "primary" ? colors.brandPrimary : variant === "secondary" ? colors.brandSecondary : "transparent";
  const fg =
    variant === "primary" ? colors.onBrandPrimary : variant === "secondary" ? colors.onBrandSecondary : colors.brandPrimary;
  return (
    <Pressable
      testID={testID}
      disabled={disabled || loading}
      onPress={() => {
        Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light).catch(() => {});
        onPress();
      }}
      style={({ pressed }) => [
        {
          backgroundColor: bg,
          borderRadius: radius.md,
          paddingVertical: spacing.md + 2,
          paddingHorizontal: spacing.lg,
          flexDirection: "row",
          alignItems: "center",
          justifyContent: "center",
          gap: spacing.sm,
          borderWidth: variant === "outline" ? 1.5 : 0,
          borderColor: colors.brandPrimary,
          opacity: disabled ? 0.5 : 1,
        },
        pressed && { opacity: 0.85 },
        style,
      ]}
    >
      {loading ? (
        <ActivityIndicator color={fg} />
      ) : (
        <>
          {icon && <Ionicons name={icon} size={18} color={fg} />}
          <Text style={{ color: fg, fontSize: 16, ...fonts.face("text", "700") }}>{title}</Text>
        </>
      )}
    </Pressable>
  );
}

export function Field({
  label,
  value,
  onChangeText,
  placeholder,
  keyboardType,
  secureTextEntry,
  autoCapitalize,
  multiline,
  testID,
  onFocus,
}: {
  label?: string;
  value: string;
  onChangeText: (t: string) => void;
  placeholder?: string;
  keyboardType?: "default" | "email-address" | "numeric" | "decimal-pad";
  secureTextEntry?: boolean;
  autoCapitalize?: "none" | "sentences" | "words" | "characters";
  multiline?: boolean;
  testID?: string;
  onFocus?: () => void;
}) {
  const { colors, radius, spacing, fonts, fontSize } = useTheme();
  return (
    <View style={{ gap: spacing.xs }}>
      {label ? <AppText variant="label">{label}</AppText> : null}
      <TextInput
        testID={testID}
        value={value}
        onChangeText={onChangeText}
        onFocus={onFocus}
        placeholder={placeholder}
        placeholderTextColor={colors.onSurfaceTertiary}
        keyboardType={keyboardType}
        secureTextEntry={secureTextEntry}
        autoCapitalize={autoCapitalize}
        multiline={multiline}
        style={{
          backgroundColor: colors.surfaceTertiary,
          borderRadius: radius.md,
          paddingHorizontal: spacing.lg,
          paddingVertical: spacing.md + 2,
          fontSize: fontSize.lg,
          color: colors.onSurface,
          fontFamily: fonts.text,
          minHeight: multiline ? 90 : 52,
          textAlignVertical: multiline ? "top" : "center",
          borderWidth: 1,
          borderColor: colors.border,
        }}
      />
    </View>
  );
}

export function Pill({ label, tone = "neutral", testID }: { label: string; tone?: "neutral" | "success" | "warning" | "info"; testID?: string }) {
  const { colors, radius, spacing, fonts } = useTheme();
  const toneMap = {
    neutral: { bg: colors.brandTertiary, fg: colors.onBrandTertiary },
    success: { bg: colors.success, fg: colors.onSuccess },
    warning: { bg: colors.warning, fg: colors.onWarning },
    info: { bg: colors.info, fg: colors.onInfo },
  } as const;
  const t = toneMap[tone];
  return (
    <View
      testID={testID}
      style={{ backgroundColor: t.bg, borderRadius: radius.pill, paddingHorizontal: spacing.md, paddingVertical: 4 }}
    >
      <Text style={{ color: t.fg, fontSize: 12, ...fonts.face("text", "700") }}>{label}</Text>
    </View>
  );
}

export function EmptyState({
  icon,
  title,
  subtitle,
  testID,
}: {
  icon: keyof typeof Ionicons.glyphMap;
  title: string;
  subtitle?: string;
  testID?: string;
}) {
  const { colors, spacing } = useTheme();
  return (
    <View testID={testID} style={{ alignItems: "center", paddingVertical: spacing["3xl"], gap: spacing.sm }}>
      <View
        style={{
          width: 72,
          height: 72,
          borderRadius: 36,
          backgroundColor: colors.brandTertiary,
          alignItems: "center",
          justifyContent: "center",
          marginBottom: spacing.sm,
        }}
      >
        <Ionicons name={icon} size={32} color={colors.brand} />
      </View>
      <AppText variant="heading" style={{ textAlign: "center" }}>
        {title}
      </AppText>
      {subtitle ? (
        <AppText variant="caption" style={{ textAlign: "center", maxWidth: 260 }}>
          {subtitle}
        </AppText>
      ) : null}
    </View>
  );
}

export function Divider() {
  const { colors, spacing } = useTheme();
  return <View style={{ height: 1, backgroundColor: colors.divider, marginVertical: spacing.md }} />;
}

export function IconButton({
  icon,
  onPress,
  color,
  testID,
  size = 22,
}: {
  icon: keyof typeof Ionicons.glyphMap;
  onPress: () => void;
  color?: string;
  testID?: string;
  size?: number;
}) {
  const { colors } = useTheme();
  return (
    <Pressable
      testID={testID}
      onPress={onPress}
      hitSlop={10}
      style={({ pressed }) => [
        {
          width: 40,
          height: 40,
          borderRadius: 20,
          alignItems: "center",
          justifyContent: "center",
          backgroundColor: colors.surfaceTertiary,
        },
        pressed && { opacity: 0.6 },
      ]}
    >
      <Ionicons name={icon} size={size} color={color || colors.onSurface} />
    </Pressable>
  );
}

const styles = StyleSheet.create({});
