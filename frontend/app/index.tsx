import { useEffect } from "react";
import { View, ActivityIndicator } from "react-native";
import { useRouter } from "expo-router";
import { useAuth } from "@/src/context/AuthContext";
import { useTheme } from "@/src/theme/ThemeProvider";

export default function Index() {
  const { user, booting } = useAuth();
  const { colors } = useTheme();
  const router = useRouter();

  useEffect(() => {
    if (booting) return;
    if (user) router.replace("/(tabs)");
    else router.replace("/(auth)/login");
  }, [user, booting]);

  return (
    <View style={{ flex: 1, alignItems: "center", justifyContent: "center", backgroundColor: colors.surface }}>
      <ActivityIndicator color={colors.brand} size="large" />
    </View>
  );
}
