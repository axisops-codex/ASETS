import React, { useCallback, useMemo, useState } from "react";
import { View, ScrollView, Pressable, ActivityIndicator } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { useFocusEffect, useRouter } from "expo-router";
import { Ionicons } from "@expo/vector-icons";
import * as Haptics from "expo-haptics";
import { useTheme } from "@/src/theme/ThemeProvider";
import { useScreenBottomPadding } from "@/src/hooks/use-tab-bar-height";
import { api } from "@/src/api/client";
import { useToast } from "@/src/components/Toast";
import { AppText, Card, EmptyState, IconButton } from "@/src/components/ui";
import { gbp, prettyDate } from "@/src/utils/format";

export default function Payments() {
  const { colors, spacing } = useTheme();
  const insets = useSafeAreaInsets();
  const bottomPadding = useScreenBottomPadding(40);
  const router = useRouter();
  const toast = useToast();

  const [invoices, setInvoices] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    try {
      setInvoices(await api.invoices());
    } catch (e: any) {
      toast.show(e.message || "Could not load", "error");
    } finally {
      setLoading(false);
    }
  }, []);

  useFocusEffect(useCallback(() => { load(); }, [load]));

  const { owedByClient, totalOwed, recentPaid } = useMemo(() => {
    const unpaid = invoices.filter((i) => i.status !== "paid");
    const groups: Record<string, { name: string; total: number; items: any[] }> = {};
    unpaid.forEach((i) => {
      const key = i.client_id || i.client_name;
      groups[key] = groups[key] || { name: i.client_name, total: 0, items: [] };
      groups[key].total += i.total || 0;
      groups[key].items.push(i);
    });
    const owed = Object.values(groups).sort((a, b) => b.total - a.total);
    const total = unpaid.reduce((s, i) => s + (i.total || 0), 0);
    const paid = invoices
      .filter((i) => i.status === "paid")
      .sort((a, b) => (a.paid_date || "") < (b.paid_date || "") ? 1 : -1)
      .slice(0, 8);
    return { owedByClient: owed, totalOwed: total, recentPaid: paid };
  }, [invoices]);

  const markPaid = async (id: string) => {
    Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success).catch(() => {});
    try {
      await api.updateInvoice(id, { status: "paid" });
      toast.show("Marked as paid", "success");
      load();
    } catch (e: any) {
      toast.show(e.message, "error");
    }
  };

  return (
    <View style={{ flex: 1, backgroundColor: colors.surface }}>
      <View style={{ paddingTop: insets.top + spacing.sm, paddingHorizontal: spacing.lg, paddingBottom: spacing.md, backgroundColor: colors.surface, borderBottomWidth: 1, borderBottomColor: colors.border, flexDirection: "row", alignItems: "center", gap: spacing.sm }}>
        <IconButton icon="chevron-back" onPress={() => router.back()} testID="payments-back-button" />
        <AppText variant="title">Payments</AppText>
      </View>

      {loading ? (
        <View style={{ flex: 1, alignItems: "center", justifyContent: "center" }}>
          <ActivityIndicator color={colors.brand} size="large" />
        </View>
      ) : (
        <ScrollView contentContainerStyle={{ padding: spacing.lg, paddingBottom: bottomPadding, gap: spacing.lg }} showsVerticalScrollIndicator={false}>
          <Card style={{ backgroundColor: colors.brandSecondary, borderColor: colors.brandSecondary }} testID="payments-total-owed">
            <AppText variant="label" color={colors.onBrandSecondary} style={{ opacity: 0.9 }}>Still owed to you</AppText>
            <AppText variant="mono" color={colors.onBrandSecondary}>{gbp(totalOwed)}</AppText>
          </Card>

          <AppText variant="label">Who owes you</AppText>
          {owedByClient.length === 0 ? (
            <EmptyState icon="checkmark-done-circle-outline" title="All paid up!" subtitle="Every invoice has been paid. Nice work." testID="payments-empty-owed" />
          ) : (
            owedByClient.map((g) => (
              <Card key={g.name} testID={`owed-client-${g.name}`}>
                <View style={{ flexDirection: "row", justifyContent: "space-between", alignItems: "center", marginBottom: spacing.sm }}>
                  <AppText variant="heading">{g.name}</AppText>
                  <AppText variant="heading" color={colors.warning}>{gbp(g.total)}</AppText>
                </View>
                {g.items.map((inv: any) => (
                  <View key={inv.id} style={{ flexDirection: "row", alignItems: "center", gap: spacing.sm, paddingVertical: 6 }}>
                    <View style={{ flex: 1 }}>
                      <AppText variant="body">{inv.number} · {gbp(inv.total)}</AppText>
                      <AppText variant="caption">Issued {prettyDate(inv.issue_date)}{inv.due_date ? ` · Due ${prettyDate(inv.due_date)}` : ""}</AppText>
                    </View>
                    <Pressable
                      testID={`mark-paid-${inv.id}`}
                      onPress={() => markPaid(inv.id)}
                      style={({ pressed }) => [{ flexDirection: "row", alignItems: "center", gap: 4, backgroundColor: colors.success, paddingHorizontal: spacing.md, paddingVertical: spacing.sm, borderRadius: 999 }, pressed && { opacity: 0.8 }]}
                    >
                      <Ionicons name="checkmark" size={15} color={colors.onSuccess} />
                      <AppText variant="caption" color={colors.onSuccess} style={{ fontWeight: "700" }}>Paid</AppText>
                    </Pressable>
                  </View>
                ))}
              </Card>
            ))
          )}

          {recentPaid.length > 0 && (
            <>
              <AppText variant="label">Recently paid</AppText>
              <Card style={{ gap: 0 }}>
                {recentPaid.map((inv: any, i: number) => (
                  <View key={inv.id}>
                    <View style={{ flexDirection: "row", alignItems: "center", justifyContent: "space-between", paddingVertical: spacing.sm }}>
                      <View style={{ flex: 1 }}>
                        <AppText variant="body" style={{ fontWeight: "600" }}>{inv.client_name}</AppText>
                        <AppText variant="caption">{inv.number} · Paid {prettyDate(inv.paid_date)}</AppText>
                      </View>
                      <AppText variant="body" color={colors.success} style={{ fontWeight: "700" }}>{gbp(inv.total)}</AppText>
                    </View>
                    {i < recentPaid.length - 1 && <View style={{ height: 1, backgroundColor: colors.divider }} />}
                  </View>
                ))}
              </Card>
            </>
          )}
        </ScrollView>
      )}
    </View>
  );
}
