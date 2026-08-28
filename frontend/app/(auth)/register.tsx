import React, { useState } from "react";
import { View, Pressable } from "react-native";
import { KeyboardAwareScrollView } from "react-native-keyboard-controller";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { useRouter } from "expo-router";
import { Ionicons } from "@expo/vector-icons";
import { useTheme } from "@/src/theme/ThemeProvider";
import { useAuth } from "@/src/context/AuthContext";
import { useToast } from "@/src/components/Toast";
import { AppText, Field, PrimaryButton, IconButton } from "@/src/components/ui";
import { LogoMark } from "@/src/components/Logo";

export default function Register() {
  const { colors, spacing } = useTheme();
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const { register } = useAuth();
  const toast = useToast();

  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);

  const onSubmit = async () => {
    if (!email.trim() || password.length < 6) {
      toast.show("Use a valid email and 6+ char password", "error");
      return;
    }
    setLoading(true);
    try {
      await register(email.trim(), password, name.trim());
      router.replace("/(tabs)");
    } catch (e: any) {
      toast.show(e.message || "Could not create account", "error");
    } finally {
      setLoading(false);
    }
  };

  return (
    <View style={{ flex: 1, backgroundColor: colors.surface }}>
      <KeyboardAwareScrollView
        bottomOffset={24}
        contentContainerStyle={{ padding: spacing.xl, paddingTop: insets.top + spacing.lg, gap: spacing.lg }}
        keyboardShouldPersistTaps="handled"
      >
        <View style={{ flexDirection: "row", marginBottom: spacing.sm }}>
          <IconButton icon="chevron-back" onPress={() => router.back()} testID="register-back-button" />
        </View>
        <View style={{ gap: spacing.sm, marginBottom: spacing.md }}>
          <View style={{ marginBottom: spacing.sm }}>
            <LogoMark size={52} />
          </View>
          <AppText variant="display">Create account</AppText>
          <AppText variant="body" color={colors.onSurfaceTertiary}>
            Join ASETS — your data stays private to you.
          </AppText>
        </View>

        <Field label="Your name" value={name} onChangeText={setName} placeholder="e.g. Dr. Sarah Jones" autoCapitalize="words" testID="register-name-input" />
        <Field label="Email" value={email} onChangeText={setEmail} placeholder="you@example.com" keyboardType="email-address" autoCapitalize="none" testID="register-email-input" />
        <Field label="Password" value={password} onChangeText={setPassword} placeholder="6+ characters" secureTextEntry autoCapitalize="none" testID="register-password-input" />

        <PrimaryButton title="Create account" onPress={onSubmit} loading={loading} testID="register-submit-button" />

        <Pressable onPress={() => router.back()} style={{ alignItems: "center", paddingVertical: spacing.md }} testID="go-to-login-button">
          <AppText variant="body" color={colors.onSurfaceTertiary}>
            Already have an account? <AppText variant="body" color={colors.brand}>Sign in</AppText>
          </AppText>
        </Pressable>
      </KeyboardAwareScrollView>
    </View>
  );
}
