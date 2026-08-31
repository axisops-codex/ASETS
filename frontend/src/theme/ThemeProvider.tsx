import React, { createContext, useContext, useEffect, useMemo, useState } from "react";
import { useColorScheme, TextStyle } from "react-native";
import { useFonts } from "expo-font";
import { storage } from "@/src/utils/storage";
import { palette, spacing, radius, fontSize, ThemeColors } from "./tokens";

type Mode = "light" | "dark" | "system";
type Weight = TextStyle["fontWeight"];
type Role = "display" | "text";

export type Fonts = {
  display?: string;
  text?: string;
  /**
   * fontFamily + fontWeight for a role at a given weight. Each bundled face
   * carries its own weight, so once they load the numeric weight is dropped —
   * leaving it on makes the renderer synthesise a second layer of bold over an
   * already-bold face. Until they load (or if they fail) the family is absent
   * and the weight is what keeps the hierarchy on the system font.
   */
  face: (role: Role, weight?: Weight) => TextStyle;
};

// Weight -> face. Text ships the five weights the design uses; display is only
// ever set in 700, so every display weight collapses onto the one bold face.
const TEXT_FACES: Record<number, string> = {
  400: "PlusJakartaSans_400Regular",
  500: "PlusJakartaSans_500Medium",
  600: "PlusJakartaSans_600SemiBold",
  700: "PlusJakartaSans_700Bold",
  800: "PlusJakartaSans_800ExtraBold",
};
const DISPLAY_FACE = "SpaceGrotesk_700Bold";
const TEXT_STEPS = Object.keys(TEXT_FACES).map(Number);

const NAMED_WEIGHTS: Record<string, number> = {
  thin: 100, ultralight: 200, light: 300, regular: 400, normal: 400,
  medium: 500, semibold: 600, bold: 700, heavy: 800, black: 900,
};

const numeric = (w?: Weight): number => {
  if (w == null) return 400;
  const named = NAMED_WEIGHTS[String(w)];
  if (named) return named;
  const n = Number(w);
  return Number.isFinite(n) ? n : 400;
};

const nearestFace = (w?: Weight): string =>
  TEXT_FACES[TEXT_STEPS.reduce((best, step) =>
    Math.abs(step - numeric(w)) < Math.abs(best - numeric(w)) ? step : best)];

const THEME_KEY = "psybooks_theme_mode";
const Ctx = createContext<ThemeCtx | null>(null);

type ThemeCtx = {
  colors: ThemeColors;
  scheme: "light" | "dark";
  mode: Mode;
  setMode: (m: Mode) => void;
  spacing: typeof spacing;
  radius: typeof radius;
  fontSize: typeof fontSize;
  fonts: Fonts;
};

export function ThemeProvider({ children }: { children: React.ReactNode }) {
  const system = useColorScheme();
  const [mode, setModeState] = useState<Mode>("system");

  // Bundled, not fetched. These used to come from a CDN, and when that URL
  // 404s the whole app silently falls back to the system font — the brand
  // disappears with no error anywhere, and offline it never appears at all.
  const [fontsLoaded] = useFonts({
    [DISPLAY_FACE]: require("@/assets/fonts/SpaceGrotesk_700Bold.ttf"),
    PlusJakartaSans_400Regular: require("@/assets/fonts/PlusJakartaSans_400Regular.ttf"),
    PlusJakartaSans_500Medium: require("@/assets/fonts/PlusJakartaSans_500Medium.ttf"),
    PlusJakartaSans_600SemiBold: require("@/assets/fonts/PlusJakartaSans_600SemiBold.ttf"),
    PlusJakartaSans_700Bold: require("@/assets/fonts/PlusJakartaSans_700Bold.ttf"),
    PlusJakartaSans_800ExtraBold: require("@/assets/fonts/PlusJakartaSans_800ExtraBold.ttf"),
  });

  useEffect(() => {
    storage.getItem<string>(THEME_KEY, "system").then((m) => {
      if (m === "light" || m === "dark" || m === "system") setModeState(m);
    });
  }, []);

  const setMode = (m: Mode) => {
    setModeState(m);
    storage.setItem(THEME_KEY, m);
  };

  const scheme: "light" | "dark" = mode === "system" ? (system === "dark" ? "dark" : "light") : mode;

  const value = useMemo<ThemeCtx>(
    () => ({
      colors: palette[scheme],
      scheme,
      mode,
      setMode,
      spacing,
      radius,
      fontSize,
      fonts: {
        display: fontsLoaded ? DISPLAY_FACE : undefined,
        text: fontsLoaded ? TEXT_FACES[400] : undefined,
        face: (role, weight) =>
          fontsLoaded
            ? { fontFamily: role === "display" ? DISPLAY_FACE : nearestFace(weight), fontWeight: undefined }
            : { fontWeight: weight },
      },
    }),
    [scheme, mode, fontsLoaded]
  );

  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useTheme() {
  const ctx = useContext(Ctx);
  if (!ctx) throw new Error("useTheme must be used within ThemeProvider");
  return ctx;
}
