import React, { useCallback, useState } from "react";
import { View, ScrollView, RefreshControl, Pressable, ActivityIndicator } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { useFocusEffect, useRouter } from "expo-router";
import { Ionicons } from "@expo/vector-icons";
import { useTheme } from "@/src/theme/ThemeProvider";
import { useAuth } from "@/src/context/AuthContext";
import { api } from "@/src/api/client";
import { AppText, Card, IconButton } from "@/src/components/ui";
import { gbp, fiscalYearRange, prettyMonth } from "@/src/utils/format";

export default function Dashboard() {
  const { colors, spacing, radius } = useTheme();
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const { user } = useAuth();

  const fy = fiscalYearRange();
  const [summary, setSummary] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);

  const cards: string[] = user?.settings?.cards || ["take_home", "hmrc", "cashflow", "recent"];

  const load = useCallback(async () => {
    try {
      const s = await api.summary(fy.start, fy.end);
      setSummary(s);
    } catch {
      // silent — show empty state
    } finally {
      setLoading(false);
    }
  }, [fy.start, fy.end]);

  useFocusEffect(
    useCallback(() => {
      load();
    }, [load])
  );

  const onRefresh = async () => {
    setRefreshing(true);
    await load();
    setRefreshing(false);
  };

  const tax = summary?.tax;
  const firstName = (user?.name || "").split(" ")[0] || "there";

  return (
    <View style={{ flex: 1, backgroundColor: colors.surface }}>
      {/* Sticky header */}
      <View style={{ paddingTop: insets.top + spacing.sm, paddingHorizontal: spacing.lg, paddingBottom: spacing.md, backgroundColor: colors.surface }}>
        <View style={{ flexDirection: "row", justifyContent: "space-between", alignItems: "center" }}>
          <View>
            <AppText variant="caption">Hello,</AppText>
            <AppText variant="title" testID="dashboard-greeting">{firstName} 👋</AppText>
          </View>
          <View style={{ flexDirection: "row", gap: spacing.sm }}>
            <IconButton icon="people-outline" onPress={() => router.push("/clients")} testID="open-clients-button" />
            <IconButton icon="settings-outline" onPress={() => router.push("/settings")} testID="open-settings-button" />
          </View>
        </View>
      </View>

      {loading ? (
        <View style={{ flex: 1, alignItems: "center", justifyContent: "center" }}>
          <ActivityIndicator color={colors.brand} size="large" />
        </View>
      ) : (
        <ScrollView
          contentContainerStyle={{ padding: spacing.lg, paddingTop: spacing.xs, paddingBottom: 140, gap: spacing.lg }}
          showsVerticalScrollIndicator={false}
          refreshControl={<RefreshControl refreshing={refreshing} onRefresh={onRefresh} tintColor={colors.brand} />}
        >
          {cards.includes("take_home") && (
            <Card style={{ backgroundColor: colors.brandPrimary, borderColor: colors.brandPrimary }} testID="card-take-home">
              <AppText variant="label" color={colors.onBrandPrimary} style={{ opacity: 0.9 }}>
                Estimated take home · {fy.label}
              </AppText>
              <AppText variant="mono" color={colors.onBrandPrimary} style={{ marginVertical: spacing.xs }}>
                {gbp(tax?.take_home ?? 0, 0)}
              </AppText>
              <View style={{ flexDirection: "row", gap: spacing.lg, marginTop: spacing.sm }}>
                <View>
                  <AppText variant="caption" color={colors.onBrandPrimary} style={{ opacity: 0.85 }}>Money in</AppText>
                  <AppText variant="body" color={colors.onBrandPrimary} style={{ fontWeight: "700" }}>{gbp(summary?.sales ?? 0, 0)}</AppText>
                </View>
                <View>
                  <AppText variant="caption" color={colors.onBrandPrimary} style={{ opacity: 0.85 }}>Money out</AppText>
                  <AppText variant="body" color={colors.onBrandPrimary} style={{ fontWeight: "700" }}>{gbp(summary?.expenses ?? 0, 0)}</AppText>
                </View>
                <View>
                  <AppText variant="caption" color={colors.onBrandPrimary} style={{ opacity: 0.85 }}>Set aside tax</AppText>
                  <AppText variant="body" color={colors.onBrandPrimary} style={{ fontWeight: "700" }}>{gbp(tax?.total_due ?? 0, 0)}</AppText>
                </View>
              </View>
            </Card>
          )}

          {/* Quick add */}
          <View style={{ flexDirection: "row", gap: spacing.md }}>
            <QuickAction icon="add-circle" label="New invoice" onPress={() => router.push("/(tabs)/invoices?new=1")} testID="quick-add-invoice" />
            <QuickAction icon="receipt" label="Add expense" onPress={() => router.push("/(tabs)/expenses?new=1")} tone="secondary" testID="quick-add-expense" />
          </View>

          {cards.includes("hmrc") && (
            <Card onPress={() => router.push("/(tabs)/tax")} testID="card-hmrc">
              <View style={{ flexDirection: "row", justifyContent: "space-between", alignItems: "center", marginBottom: spacing.sm }}>
                <AppText variant="heading">HMRC estimate</AppText>
                <Ionicons name="chevron-forward" size={18} color={colors.onSurfaceTertiary} />
              </View>
              <ReceiptLine label="Taxable profit" value={gbp(tax?.profit ?? 0)} colors={colors} />
              <ReceiptLine label="Income tax" value={gbp(tax?.income_tax ?? 0)} colors={colors} />
              <ReceiptLine label="National Insurance" value={gbp(tax?.national_insurance ?? 0)} colors={colors} />
              <View style={{ height: 1, backgroundColor: colors.divider, marginVertical: spacing.sm }} />
              <View style={{ flexDirection: "row", justifyContent: "space-between", alignItems: "center" }}>
                <AppText variant="label" color={colors.onSurface}>Tax to set aside</AppText>
                <AppText variant="heading" color={colors.brandSecondary}>{gbp(tax?.total_due ?? 0)}</AppText>
              </View>
            </Card>
          )}

          {cards.includes("cashflow") && (
            <Card testID="card-cashflow">
              <AppText variant="heading" style={{ marginBottom: spacing.md }}>Cash flow</AppText>
              {summary?.cashflow?.length ? (
                <CashflowChart data={summary.cashflow} colors={colors} radius={radius} />
              ) : (
                <AppText variant="caption">No activity yet this year.</AppText>
              )}
            </Card>
          )}

          {cards.includes("recent") && (
            <Card testID="card-outstanding" onPress={() => router.push("/payments")}>
              <View style={{ flexDirection: "row", justifyContent: "space-between", alignItems: "center", marginBottom: spacing.sm }}>
                <AppText variant="heading">Payments</AppText>
                <Ionicons name="chevron-forward" size={18} color={colors.onSurfaceTertiary} />
              </View>
              <View style={{ flexDirection: "row", justifyContent: "space-between" }}>
                <View style={{ flex: 1 }}>
                  <AppText variant="caption">Awaiting payment</AppText>
                  <AppText variant="heading" color={colors.warning}>{gbp(summary?.outstanding ?? 0)}</AppText>
                </View>
                <View style={{ width: 1, backgroundColor: colors.divider, marginHorizontal: spacing.md }} />
                <View style={{ flex: 1 }}>
                  <AppText variant="caption">Paid this year</AppText>
                  <AppText variant="heading" color={colors.success}>{gbp(summary?.paid ?? 0)}</AppText>
                </View>
              </View>
            </Card>
          )}
        </ScrollView>
      )}
    </View>
  );
}

function QuickAction({ icon, label, onPress, tone = "primary", testID }: any) {
  const { colors, radius, spacing, fonts } = useTheme();
  const bg = tone === "primary" ? colors.brandTertiary : colors.surfaceSecondary;
  const fg = tone === "primary" ? colors.onBrandTertiary : colors.brandSecondary;
  return (
    <Pressable
      testID={testID}
      onPress={onPress}
      style={({ pressed }) => [
        {
          flex: 1,
          backgroundColor: bg,
          borderRadius: radius.md,
          padding: spacing.md,
          flexDirection: "row",
          alignItems: "center",
          gap: spacing.sm,
          borderWidth: 1,
          borderColor: colors.border,
        },
        pressed && { opacity: 0.7 },
      ]}
    >
      <Ionicons name={icon} size={22} color={fg} />
      <AppText variant="body" color={colors.onSurface} style={{ fontWeight: "600", fontSize: 14 }}>{label}</AppText>
    </Pressable>
  );
}

function ReceiptLine({ label, value, colors }: any) {
  return (
    <View style={{ flexDirection: "row", justifyContent: "space-between", paddingVertical: 4 }}>
      <AppText variant="body" color={colors.onSurfaceTertiary}>{label}</AppText>
      <AppText variant="body" color={colors.onSurface} style={{ fontWeight: "600" }}>{value}</AppText>
    </View>
  );
}

function CashflowChart({ data, colors, radius }: any) {
  const max = Math.max(...data.map((d: any) => Math.max(d.income, d.expenses)), 1);
  return (
    <View style={{ gap: 14 }}>
      <View style={{ flexDirection: "row", alignItems: "flex-end", justifyContent: "space-around", height: 120, gap: 8 }}>
        {data.slice(-6).map((d: any, i: number) => (
          <View key={i} style={{ flex: 1, alignItems: "center", gap: 4 }}>
            <View style={{ flexDirection: "row", alignItems: "flex-end", gap: 3, height: 100 }}>
              <View style={{ width: 10, height: Math.max(4, (d.income / max) * 100), backgroundColor: colors.success, borderRadius: 3 }} />
              <View style={{ width: 10, height: Math.max(4, (d.expenses / max) * 100), backgroundColor: colors.brandSecondary, borderRadius: 3 }} />
            </View>
            <AppText variant="caption" style={{ fontSize: 10 }}>{prettyMonth(d.month)}</AppText>
          </View>
        ))}
      </View>
      <View style={{ flexDirection: "row", gap: 16, justifyContent: "center" }}>
        <Legend color={colors.success} label="In" />
        <Legend color={colors.brandSecondary} label="Out" />
      </View>
    </View>
  );
}

function Legend({ color, label }: any) {
  return (
    <View style={{ flexDirection: "row", alignItems: "center", gap: 6 }}>
      <View style={{ width: 10, height: 10, borderRadius: 3, backgroundColor: color }} />
      <AppText variant="caption">{label}</AppText>
    </View>
  );
}
