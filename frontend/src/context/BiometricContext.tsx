import React, { createContext, useContext, useEffect, useRef, useState } from "react";
import { View, Modal, Pressable, AppState, AppStateStatus } from "react-native";
import { Ionicons } from "@expo/vector-icons";
import * as LocalAuthentication from "expo-local-authentication";
import { storage } from "@/src/utils/storage";
import { useTheme } from "@/src/theme/ThemeProvider";
import { useAuth } from "@/src/context/AuthContext";
import { AppText, PrimaryButton } from "@/src/components/ui";
import { LogoMark } from "@/src/components/Logo";

const PREF_KEY = "psybooks_biometric"; // "on" | "off" | ""

type BiometricCtx = {
  supported: boolean;
  enabled: boolean;
  enable: () => Promise<boolean>;
  disable: () => Promise<void>;
};

const Ctx = createContext<BiometricCtx | null>(null);

export function BiometricProvider({ children }: { children: React.ReactNode }) {
  const { colors, spacing, radius } = useTheme();
  const { user } = useAuth();

  const [supported, setSupported] = useState(false);
  const [enabled, setEnabled] = useState(false);
  const [prefSet, setPrefSet] = useState(true);
  const [unlocked, setUnlocked] = useState(true);
  const [showPrompt, setShowPrompt] = useState(false);
  const [booted, setBooted] = useState(false);
  const authing = useRef(false);

  useEffect(() => {
    (async () => {
      const hw = await LocalAuthentication.hasHardwareAsync().catch(() => false);
      const enrolled = await LocalAuthentication.isEnrolledAsync().catch(() => false);
      setSupported(hw && enrolled);
      const pref = await storage.secureGet<string>(PREF_KEY, "");
      const isSet = pref === "on" || pref === "off";
      setPrefSet(isSet);
      const en = pref === "on";
      setEnabled(en);
      setUnlocked(!en);
      setBooted(true);
    })();
  }, []);

  const authenticate = async (): Promise<boolean> => {
    if (authing.current) return false;
    authing.current = true;
    try {
      const res = await LocalAuthentication.authenticateAsync({
        promptMessage: "Unlock ASETS",
        cancelLabel: "Cancel",
      });
      if (res.success) setUnlocked(true);
      return res.success;
    } catch {
      return false;
    } finally {
      authing.current = false;
    }
  };

  // Lock on background, re-auth on foreground
  useEffect(() => {
    const sub = AppState.addEventListener("change", (s: AppStateStatus) => {
      if (!enabled) return;
      if (s === "background" || s === "inactive") {
        setUnlocked(false);
      } else if (s === "active" && !unlocked) {
        authenticate();
      }
    });
    return () => sub.remove();
  }, [enabled, unlocked]);

  // Trigger auth when locked screen shows
  useEffect(() => {
    if (booted && enabled && !unlocked && user) authenticate();
  }, [booted, enabled, unlocked, user]);

  // Auto-ask to configure after login
  useEffect(() => {
    if (booted && user && supported && !prefSet) {
      const t = setTimeout(() => setShowPrompt(true), 800);
      return () => clearTimeout(t);
    }
  }, [booted, user, supported, prefSet]);

  const enable = async (): Promise<boolean> => {
    const ok = await authenticate();
    if (ok) {
      await storage.secureSet(PREF_KEY, "on");
      setEnabled(true);
      setPrefSet(true);
      setUnlocked(true);
    }
    return ok;
  };

  const disable = async () => {
    await storage.secureSet(PREF_KEY, "off");
    setEnabled(false);
    setPrefSet(true);
    setUnlocked(true);
  };

  const dismissPrompt = async () => {
    await storage.secureSet(PREF_KEY, "off");
    setPrefSet(true);
    setShowPrompt(false);
  };

  const acceptPrompt = async () => {
    setShowPrompt(false);
    await enable();
  };

  const showLock = booted && enabled && !unlocked && !!user;

  return (
    <Ctx.Provider value={{ supported, enabled, enable, disable }}>
      {children}

      {showLock && (
        <View style={{ position: "absolute", top: 0, left: 0, right: 0, bottom: 0, backgroundColor: colors.surface, alignItems: "center", justifyContent: "center", gap: spacing.lg, zIndex: 10000 }} testID="biometric-lock">
          <LogoMark size={92} />
          <AppText variant="title">ASETS is locked</AppText>
          <AppText variant="caption">Verify it's you to continue</AppText>
          <View style={{ width: 220 }}>
            <PrimaryButton title="Unlock" icon="finger-print" onPress={authenticate} testID="biometric-unlock-button" />
          </View>
        </View>
      )}

      <Modal visible={showPrompt} transparent animationType="fade" onRequestClose={dismissPrompt}>
        <View style={{ flex: 1, backgroundColor: "rgba(0,0,0,0.5)", justifyContent: "center", padding: spacing.xl }}>
          <View style={{ backgroundColor: colors.surfaceSecondary, borderRadius: radius.lg, padding: spacing.xl, gap: spacing.md }} testID="biometric-prompt">
            <View style={{ width: 60, height: 60, borderRadius: 18, backgroundColor: colors.brandTertiary, alignItems: "center", justifyContent: "center" }}>
              <Ionicons name="finger-print" size={30} color={colors.brand} />
            </View>
            <AppText variant="title">Lock with Face ID / fingerprint?</AppText>
            <AppText variant="body" color={colors.onSurfaceTertiary}>
              Keep your finances private. You'll unlock ASETS with your face or fingerprint each time you open it.
            </AppText>
            <PrimaryButton title="Enable" icon="lock-closed-outline" onPress={acceptPrompt} testID="biometric-enable-button" />
            <Pressable onPress={dismissPrompt} style={{ alignItems: "center", paddingVertical: spacing.sm }} testID="biometric-skip-button">
              <AppText variant="body" color={colors.onSurfaceTertiary} style={{ fontWeight: "600" }}>Not now</AppText>
            </Pressable>
          </View>
        </View>
      </Modal>
    </Ctx.Provider>
  );
}

export function useBiometric() {
  const ctx = useContext(Ctx);
  if (!ctx) throw new Error("useBiometric must be used within BiometricProvider");
  return ctx;
}
