import { useSafeAreaInsets } from "react-native-safe-area-context";
import { useTheme } from "@/src/theme/ThemeProvider";

/**
 * The tab bar floats over the screens (position: absolute), so every
 * scrolling screen has to reserve room for it or its last control ends up
 * underneath — visible, but every tap lands on the tab bar instead.
 *
 * This was previously a hardcoded 140 in each tab screen, which happened
 * to clear an iPhone's home indicator and nothing else. Deriving it from
 * the bar's own measurements means the two cannot drift apart.
 */
export const TAB_BAR_CONTENT_HEIGHT = 58;   // icon + label + the bar's own padding

/** Height of the tab bar including whatever the system reserves below it. */
export function useTabBarHeight(): number {
  const insets = useSafeAreaInsets();
  const { spacing } = useTheme();
  // Mirrors CustomTabBar's own paddingBottom, so they move together.
  return TAB_BAR_CONTENT_HEIGHT + (insets.bottom > 0 ? insets.bottom : spacing.md);
}

/**
 * Bottom padding for a screen that is *not* under the tab bar.
 *
 * Android draws edge-to-edge (app.json sets edgeToEdgeEnabled), so the
 * system navigation bar sits on top of the app. A Pixel's three-button
 * bar is ~48dp; a fixed 40 or 60 leaves the last button underneath it.
 * An iPhone's home indicator is ~34, which is why this only ever showed
 * up on Android.
 */
export function useScreenBottomPadding(extra = 24): number {
  const insets = useSafeAreaInsets();
  return insets.bottom + extra;
}
