import React, { useState } from "react";
import { View, ScrollView, Pressable, Switch } from "react-native";
import { KeyboardAwareScrollView } from "react-native-keyboard-controller";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { useRouter } from "expo-router";
import { Ionicons } from "@expo/vector-icons";
import * as Haptics from "expo-haptics";
import { useTheme } from "@/src/theme/ThemeProvider";
import { useAuth } from "@/src/context/AuthContext";
import { useBiometric } from "@/src/context/BiometricContext";
import { api } from "@/src/api/client";
import { useToast } from "@/src/components/Toast";
import { AppText, Card, Field, PrimaryButton, IconButton, Divider } from "@/src/components/ui";

const CARD_OPTIONS = [
  { key: "take_home", label: "Estimated take home", icon: "wallet-outline" },
  { key: "hmrc", label: "HMRC estimate", icon: "calculator-outline" },
  { key: "cashflow", label: "Cash flow chart", icon: "bar-chart-outline" },
  { key: "recent", label: "Paid vs outstanding", icon: "swap-horizontal-outline" },
];

export default function Settings() {
  const { colors, spacing, mode, setMode, scheme } = useTheme();
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const { user, logout, refreshUser } = useAuth();
  const { supported: bioSupported, enabled: bioEnabled, enable: bioEnable, disable: bioDisable } = useBiometric();
  const toast = useToast();

  const [name, setName] = useState(user?.name || "");
  const [business, setBusiness] = useState(user?.business_name || "");
  const [address, setAddress] = useState(user?.address || "");
  const [utr, setUtr] = useState(user?.utr || "");
  const [savingProfile, setSavingProfile] = useState(false);

  const activeCards: string[] = user?.settings?.cards || CARD_OPTIONS.map((c) => c.key);

  const saveProfile = async () => {
    setSavingProfile(true);
    try {
      const updated = await api.updateProfile({ name, business_name: business, address, utr });
      refreshUser(updated);
      toast.show("Profile saved", "success");
    } catch (e: any) {
      toast.show(e.message || "Could not save", "error");
    } finally {
      setSavingProfile(false);
    }
  };

  const toggleCard = async (key: string) => {
    Haptics.selectionAsync().catch(() => {});
    const next = activeCards.includes(key) ? activeCards.filter((k) => k !== key) : [...activeCards, key];
    const settings = { ...(user?.settings || {}), cards: next };
    try {
      const updated = await api.updateProfile({ settings });
      refreshUser(updated);
    } catch (e: any) {
      toast.show(e.message, "error");
    }
  };

  const setTheme = async (m: "light" | "dark" | "system") => {
    Haptics.selectionAsync().catch(() => {});
    setMode(m);
    const settings = { ...(user?.settings || {}), theme: m };
    api.updateProfile({ settings }).then(refreshUser).catch(() => {});
  };

  const toggleBiometric = async () => {
    Haptics.selectionAsync().catch(() => {});
    if (bioEnabled) {
      await bioDisable();
      toast.show("App lock turned off", "success");
    } else {
      const ok = await bioEnable();
      if (ok) toast.show("App lock turned on", "success");
      else toast.show("Could not verify — try again", "error");
    }
  };

  return (
    <View style={{ flex: 1, backgroundColor: colors.surface }}>
      <View style={{ paddingTop: insets.top + spacing.sm, paddingHorizontal: spacing.lg, paddingBottom: spacing.md, backgroundColor: colors.surface, borderBottomWidth: 1, borderBottomColor: colors.border, flexDirection: "row", alignItems: "center", gap: spacing.sm }}>
        <IconButton icon="chevron-back" onPress={() => router.back()} testID="settings-back-button" />
        <AppText variant="title">Settings</AppText>
      </View>

      <KeyboardAwareScrollView bottomOffset={24} contentContainerStyle={{ padding: spacing.lg, paddingBottom: 60, gap: spacing.lg }} keyboardShouldPersistTaps="handled">
        {/* Appearance */}
        <View style={{ gap: spacing.sm }}>
          <AppText variant="label">Appearance</AppText>
          <Card style={{ flexDirection: "row", gap: spacing.sm }}>
            {(["light", "dark", "system"] as const).map((m) => {
              const active = mode === m;
              const icon = m === "light" ? "sunny-outline" : m === "dark" ? "moon-outline" : "phone-portrait-outline";
              return (
                <Pressable
                  key={m}
                  testID={`theme-${m}`}
                  onPress={() => setTheme(m)}
                  style={{ flex: 1, alignItems: "center", gap: 6, paddingVertical: spacing.md, borderRadius: 12, backgroundColor: active ? colors.brandTertiary : colors.surfaceTertiary, borderWidth: 1, borderColor: active ? colors.brand : colors.border }}
                >
                  <Ionicons name={icon as any} size={22} color={active ? colors.brand : colors.onSurfaceTertiary} />
                  <AppText variant="caption" color={active ? colors.brand : colors.onSurfaceTertiary} style={{ fontWeight: "700", textTransform: "capitalize" }}>{m}</AppText>
                </Pressable>
              );
            })}
          </Card>
        </View>

        {/* Dashboard cards */}
        <View style={{ gap: spacing.sm }}>
          <AppText variant="label">Dashboard cards</AppText>
          <Card style={{ gap: 0 }}>
            {CARD_OPTIONS.map((c, i) => (
              <View key={c.key}>
                <View style={{ flexDirection: "row", alignItems: "center", gap: spacing.md, paddingVertical: spacing.sm }}>
                  <View style={{ width: 36, height: 36, borderRadius: 10, backgroundColor: colors.brandTertiary, alignItems: "center", justifyContent: "center" }}>
                    <Ionicons name={c.icon as any} size={18} color={colors.brand} />
                  </View>
                  <AppText variant="body" style={{ flex: 1, fontWeight: "600" }}>{c.label}</AppText>
                  <Switch
                    testID={`card-toggle-${c.key}`}
                    value={activeCards.includes(c.key)}
                    onValueChange={() => toggleCard(c.key)}
                    trackColor={{ true: colors.brand, false: colors.borderStrong }}
                    thumbColor="#fff"
                  />
                </View>
                {i < CARD_OPTIONS.length - 1 && <View style={{ height: 1, backgroundColor: colors.divider }} />}
              </View>
            ))}
          </Card>
        </View>

        {/* Security */}
        <View style={{ gap: spacing.sm }}>
          <AppText variant="label">Security</AppText>
          <Card>
            <View style={{ flexDirection: "row", alignItems: "center", gap: spacing.md }}>
              <View style={{ width: 36, height: 36, borderRadius: 10, backgroundColor: colors.brandTertiary, alignItems: "center", justifyContent: "center" }}>
                <Ionicons name="finger-print" size={18} color={colors.brand} />
              </View>
              <View style={{ flex: 1 }}>
                <AppText variant="body" style={{ fontWeight: "600" }}>Unlock with Face ID / fingerprint</AppText>
                <AppText variant="caption">{bioSupported ? "Require biometrics to open the app" : "Set up Face ID or a fingerprint on your device first"}</AppText>
              </View>
              <Switch
                testID="biometric-toggle"
                value={bioEnabled}
                disabled={!bioSupported}
                onValueChange={toggleBiometric}
                trackColor={{ true: colors.brand, false: colors.borderStrong }}
                thumbColor="#fff"
              />
            </View>
          </Card>
        </View>

        {/* Business profile */}
        <View style={{ gap: spacing.sm }}>
          <AppText variant="label">Your details (shown on invoices)</AppText>
          <Card style={{ gap: spacing.md }}>
            <Field label="Your name" value={name} onChangeText={setName} placeholder="Dr. Sarah Jones" autoCapitalize="words" testID="settings-name-input" />
            <Field label="Practice / business name" value={business} onChangeText={setBusiness} placeholder="Sarah Jones Psychology" autoCapitalize="words" testID="settings-business-input" />
            <Field label="Address" value={address} onChangeText={setAddress} placeholder="Your billing address" multiline testID="settings-address-input" />
            <Field label="UTR (optional)" value={utr} onChangeText={setUtr} placeholder="10-digit tax reference" keyboardType="numeric" testID="settings-utr-input" />
            <PrimaryButton title="Save details" onPress={saveProfile} loading={savingProfile} testID="settings-save-profile" />
          </Card>
        </View>

        <Divider />
        <View style={{ gap: spacing.xs }}>
          <AppText variant="caption">{user?.email}</AppText>
          <PrimaryButton title="Sign out" icon="log-out-outline" variant="outline" onPress={async () => { await logout(); router.replace("/(auth)/login"); }} testID="settings-logout-button" />
        </View>
      </KeyboardAwareScrollView>
    </View>
  );
}
