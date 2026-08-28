import React, { createContext, useContext, useEffect, useMemo, useState } from "react";
import { useColorScheme } from "react-native";
import { useFonts } from "expo-font";
import { storage } from "@/src/utils/storage";
import { palette, spacing, radius, fontSize, ThemeColors } from "./tokens";

type Mode = "light" | "dark" | "system";

type Fonts = { display?: string; text?: string };

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

const THEME_KEY = "psybooks_theme_mode";
const Ctx = createContext<ThemeCtx | null>(null);

export function ThemeProvider({ children }: { children: React.ReactNode }) {
  const system = useColorScheme();
  const [mode, setModeState] = useState<Mode>("system");

  const [fontsLoaded] = useFonts({
    "SpaceGrotesk": "https://cdn.jsdelivr.net/gh/google/fonts/ofl/spacegrotesk/SpaceGrotesk%5Bwght%5D.ttf",
    "PlusJakartaSans": "https://cdn.jsdelivr.net/gh/google/fonts/ofl/plusjakartasans/PlusJakartaSans%5Bwght%5D.ttf",
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
      fonts: fontsLoaded
        ? { display: "SpaceGrotesk", text: "PlusJakartaSans" }
        : {},
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
