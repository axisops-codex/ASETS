import React from "react";
import { View } from "react-native";
import Svg, { Circle, Path } from "react-native-svg";
import { useTheme } from "@/src/theme/ThemeProvider";
import { AppText } from "@/src/components/ui";

const RED = "#BC002D";
const BLUE = "#8CAFD6";

export function LogoMark({ size = 64 }: { size?: number }) {
  const s = size;
  const c = 50;
  return (
    <Svg width={s} height={s} viewBox="0 0 100 100">
      {/* soft blue ring — calm, trust */}
      <Circle cx={c} cy={c} r={43} stroke={BLUE} strokeWidth={5} fill="none" />
      {/* hinomaru red circle — focus, clarity, control */}
      <Circle cx={c} cy={c} r={34.5} fill={RED} />
      {/* white ascending check — done, moving forward */}
      <Path
        d="M34 51 L47 64 L68 36"
        stroke="#FFFFFF"
        strokeWidth={8}
        strokeLinecap="round"
        strokeLinejoin="round"
        fill="none"
      />
    </Svg>
  );
}

export function LogoLockup({ size = 64, tagline = true }: { size?: number; tagline?: boolean }) {
  const { colors, spacing } = useTheme();
  return (
    <View style={{ alignItems: "flex-start", gap: spacing.sm }}>
      <LogoMark size={size} />
      <View>
        <AppText variant="display" style={{ letterSpacing: 2 }}>ASETS</AppText>
        {tagline ? (
          <AppText variant="caption" color={colors.onSurfaceTertiary}>
            ADHD Self-Employed Taxes Support
          </AppText>
        ) : null}
      </View>
    </View>
  );
}
