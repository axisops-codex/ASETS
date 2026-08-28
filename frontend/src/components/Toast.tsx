import React, { createContext, useCallback, useContext, useRef, useState } from "react";
import { View, Text, StyleSheet } from "react-native";
import Animated, { useAnimatedStyle, useSharedValue, withTiming, withSequence } from "react-native-reanimated";
import { Ionicons } from "@expo/vector-icons";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { useTheme } from "@/src/theme/ThemeProvider";

type Tone = "success" | "error" | "info";
type ToastCtx = { show: (msg: string, tone?: Tone) => void };

const Ctx = createContext<ToastCtx | null>(null);

export function ToastProvider({ children }: { children: React.ReactNode }) {
  const { colors, radius, spacing, fonts } = useTheme();
  const insets = useSafeAreaInsets();
  const [msg, setMsg] = useState("");
  const [tone, setTone] = useState<Tone>("info");
  const opacity = useSharedValue(0);
  const translateY = useSharedValue(-20);
  const timer = useRef<any>(null);

  const show = useCallback((m: string, t: Tone = "info") => {
    setMsg(m);
    setTone(t);
    opacity.value = withTiming(1, { duration: 220 });
    translateY.value = withSequence(withTiming(0, { duration: 220 }));
    if (timer.current) clearTimeout(timer.current);
    timer.current = setTimeout(() => {
      opacity.value = withTiming(0, { duration: 220 });
      translateY.value = withTiming(-20, { duration: 220 });
    }, 2600);
  }, []);

  const style = useAnimatedStyle(() => ({ opacity: opacity.value, transform: [{ translateY: translateY.value }] }));

  const toneColor = tone === "success" ? colors.success : tone === "error" ? colors.error : colors.surfaceInverse;
  const icon = tone === "success" ? "checkmark-circle" : tone === "error" ? "alert-circle" : "information-circle";

  return (
    <Ctx.Provider value={{ show }}>
      {children}
      <Animated.View
        pointerEvents="none"
        style={[
          styles.wrap,
          { top: insets.top + spacing.sm },
          style,
        ]}
      >
        <View style={[styles.toast, { backgroundColor: toneColor, borderRadius: radius.md, paddingHorizontal: spacing.lg, paddingVertical: spacing.md }]}>
          <Ionicons name={icon as any} size={20} color={tone === "info" ? colors.onSurfaceInverse : "#fff"} />
          <Text style={{ color: tone === "info" ? colors.onSurfaceInverse : "#fff", fontFamily: fonts.text, fontWeight: "600", flexShrink: 1 }}>
            {msg}
          </Text>
        </View>
      </Animated.View>
    </Ctx.Provider>
  );
}

export function useToast() {
  const ctx = useContext(Ctx);
  if (!ctx) throw new Error("useToast must be used within ToastProvider");
  return ctx;
}

const styles = StyleSheet.create({
  wrap: { position: "absolute", left: 16, right: 16, alignItems: "center", zIndex: 9999 },
  toast: { flexDirection: "row", alignItems: "center", gap: 10, maxWidth: 500 },
});
