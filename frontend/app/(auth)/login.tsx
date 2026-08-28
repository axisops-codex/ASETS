import React, { useState } from "react";
import { View, Pressable } from "react-native";
import { KeyboardAwareScrollView } from "react-native-keyboard-controller";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { useRouter } from "expo-router";
import { Ionicons } from "@expo/vector-icons";
import { useTheme } from "@/src/theme/ThemeProvider";
import { useAuth } from "@/src/context/AuthContext";
import { useToast } from "@/src/components/Toast";
import { AppText, Field, PrimaryButton } from "@/src/components/ui";

export default function Login() {
  const { colors, spacing } = useTheme();
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const { login } = useAuth();
  const toast = useToast();

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);

  const onSubmit = async () => {
    if (!email.trim() || !password) {
      toast.show("Enter your email and password", "error");
      return;
    }
    setLoading(true);
    try {
      await login(email.trim(), password);
      router.replace("/(tabs)");
    } catch (e: any) {
      toast.show(e.message || "Could not sign in", "error");
    } finally {
      setLoading(false);
    }
  };

  return (
    <View style={{ flex: 1, backgroundColor: colors.surface }}>
      <KeyboardAwareScrollView
        bottomOffset={24}
        contentContainerStyle={{ padding: spacing.xl, paddingTop: insets.top + spacing["3xl"], gap: spacing.lg }}
        keyboardShouldPersistTaps="handled"
      >
        <View style={{ gap: spacing.sm, marginBottom: spacing.lg }}>
          <View
            style={{
              width: 60,
              height: 60,
              borderRadius: 18,
              backgroundColor: colors.brandPrimary,
              alignItems: "center",
              justifyContent: "center",
              marginBottom: spacing.md,
            }}
          >
            <Ionicons name="leaf" size={30} color={colors.onBrandPrimary} />
          </View>
          <AppText variant="display">Welcome back</AppText>
          <AppText variant="body" color={colors.onSurfaceTertiary}>
            Sign in to manage your practice finances.
          </AppText>
        </View>

        <Field
          label="Email"
          value={email}
          onChangeText={setEmail}
          placeholder="you@example.com"
          keyboardType="email-address"
          autoCapitalize="none"
          testID="login-email-input"
        />
        <Field
          label="Password"
          value={password}
          onChangeText={setPassword}
          placeholder="Your password"
          secureTextEntry
          autoCapitalize="none"
          testID="login-password-input"
        />

        <PrimaryButton title="Sign in" onPress={onSubmit} loading={loading} testID="login-submit-button" />

        <Pressable
          testID="go-to-register-button"
          onPress={() => router.push("/(auth)/register")}
          style={{ alignItems: "center", paddingVertical: spacing.md }}
        >
          <AppText variant="body" color={colors.onSurfaceTertiary}>
            New here? <AppText variant="body" color={colors.brand}>Create an account</AppText>
          </AppText>
        </Pressable>
      </KeyboardAwareScrollView>
    </View>
  );
}
