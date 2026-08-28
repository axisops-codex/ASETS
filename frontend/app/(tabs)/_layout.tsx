import React from "react";
import { View, Pressable, Platform } from "react-native";
import { Tabs } from "expo-router";
import { Ionicons } from "@expo/vector-icons";
import { BlurView } from "expo-blur";
import * as Haptics from "expo-haptics";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { useTheme } from "@/src/theme/ThemeProvider";
import { AppText } from "@/src/components/ui";

const TABS = [
  { name: "index", label: "Home", icon: "home", activeIcon: "home" },
  { name: "invoices", label: "Invoices", icon: "document-text-outline", activeIcon: "document-text" },
  { name: "expenses", label: "Expenses", icon: "receipt-outline", activeIcon: "receipt" },
  { name: "tax", label: "Tax", icon: "calculator-outline", activeIcon: "calculator" },
] as const;

function CustomTabBar({ state, navigation }: any) {
  const { colors, spacing, scheme } = useTheme();
  const insets = useSafeAreaInsets();

  return (
    <View style={{ position: "absolute", left: 0, right: 0, bottom: 0 }}>
      <BlurView
        intensity={scheme === "dark" ? 40 : 60}
        tint={scheme === "dark" ? "dark" : "light"}
        style={{
          flexDirection: "row",
          paddingBottom: insets.bottom > 0 ? insets.bottom : spacing.md,
          paddingTop: spacing.sm,
          paddingHorizontal: spacing.sm,
          borderTopWidth: 1,
          borderTopColor: colors.border,
          backgroundColor: scheme === "dark" ? "rgba(18,19,18,0.82)" : "rgba(249,249,248,0.82)",
        }}
      >
        {state.routes
          .filter((r: any) => TABS.some((t) => t.name === r.name))
          .map((route: any) => {
            const meta = TABS.find((t) => t.name === route.name)!;
            const index = state.routes.findIndex((r: any) => r.key === route.key);
            const focused = state.index === index;
            return (
              <Pressable
                key={route.key}
                testID={`tab-${meta.name}`}
                onPress={() => {
                  Haptics.selectionAsync().catch(() => {});
                  const event = navigation.emit({ type: "tabPress", target: route.key, canPreventDefault: true });
                  if (!focused && !event.defaultPrevented) navigation.navigate(route.name);
                }}
                style={{ flex: 1, alignItems: "center", justifyContent: "center", gap: 3, paddingVertical: 4 }}
              >
                <Ionicons
                  name={(focused ? meta.activeIcon : meta.icon) as any}
                  size={24}
                  color={focused ? colors.brand : colors.onSurfaceTertiary}
                />
                <AppText variant="caption" color={focused ? colors.brand : colors.onSurfaceTertiary} style={{ fontWeight: focused ? "700" : "500", fontSize: 11 }}>
                  {meta.label}
                </AppText>
              </Pressable>
            );
          })}
      </BlurView>
    </View>
  );
}

export default function TabsLayout() {
  return (
    <Tabs
      screenOptions={{ headerShown: false }}
      tabBar={(props) => <CustomTabBar {...props} />}
    >
      <Tabs.Screen name="index" />
      <Tabs.Screen name="invoices" />
      <Tabs.Screen name="expenses" />
      <Tabs.Screen name="tax" />
    </Tabs>
  );
}
