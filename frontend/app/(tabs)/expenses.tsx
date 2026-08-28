import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { View, SectionList, Pressable, ActivityIndicator, Platform } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { useFocusEffect, useLocalSearchParams, useRouter } from "expo-router";
import { Ionicons } from "@expo/vector-icons";
import DateTimePicker from "@react-native-community/datetimepicker";
import BottomSheet from "@gorhom/bottom-sheet";
import * as Haptics from "expo-haptics";
import { useTheme } from "@/src/theme/ThemeProvider";
import { api } from "@/src/api/client";
import { useToast } from "@/src/components/Toast";
import { AppSheet } from "@/src/components/AppSheet";
import { AppText, Card, Field, PrimaryButton, EmptyState, IconButton } from "@/src/components/ui";
import { gbp, prettyDate, prettyMonth, toISODate } from "@/src/utils/format";

const CATEGORIES = [
  { key: "Software", icon: "laptop-outline" },
  { key: "Supervision", icon: "people-circle-outline" },
  { key: "Training / CPD", icon: "school-outline" },
  { key: "Insurance", icon: "shield-checkmark-outline" },
  { key: "Professional fees", icon: "ribbon-outline" },
  { key: "Office / Rent", icon: "business-outline" },
  { key: "Equipment", icon: "hardware-chip-outline" },
  { key: "Phone / Internet", icon: "wifi-outline" },
  { key: "Travel", icon: "car-outline" },
  { key: "Other", icon: "ellipsis-horizontal-circle-outline" },
];

const catIcon = (c: string) => CATEGORIES.find((x) => x.key === c)?.icon || "pricetag-outline";

export default function Expenses() {
  const { colors, spacing } = useTheme();
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const params = useLocalSearchParams<{ new?: string }>();
  const toast = useToast();

  const [expenses, setExpenses] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const createRef = useRef<BottomSheet>(null);

  const [category, setCategory] = useState("Software");
  const [description, setDescription] = useState("");
  const [amount, setAmount] = useState("");
  const [date, setDate] = useState(new Date());
  const [showPicker, setShowPicker] = useState(false);
  const [saving, setSaving] = useState(false);

  const load = useCallback(async () => {
    try {
      setExpenses(await api.expenses());
    } catch (e: any) {
      toast.show(e.message || "Could not load", "error");
    } finally {
      setLoading(false);
    }
  }, []);

  useFocusEffect(useCallback(() => { load(); }, [load]));

  useEffect(() => {
    if (params.new === "1") {
      setTimeout(() => openCreate(), 300);
      router.setParams({ new: undefined });
    }
  }, [params.new]);

  const total = useMemo(() => expenses.reduce((s, e) => s + (e.amount || 0), 0), [expenses]);

  const sections = useMemo(() => {
    const groups: Record<string, any[]> = {};
    expenses.forEach((e) => {
      const m = (e.date || "").slice(0, 7);
      groups[m] = groups[m] || [];
      groups[m].push(e);
    });
    return Object.keys(groups)
      .sort((a, b) => (a < b ? 1 : -1))
      .map((m) => ({ title: m, data: groups[m] }));
  }, [expenses]);

  const openCreate = () => {
    setCategory("Software");
    setDescription("");
    setAmount("");
    setDate(new Date());
    createRef.current?.expand();
  };

  const save = async () => {
    const amt = parseFloat(amount || "0");
    if (!amt || amt <= 0) return toast.show("Enter an amount", "error");
    setSaving(true);
    try {
      await api.createExpense({ category, description, amount: amt, date: toISODate(date) });
      Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success).catch(() => {});
      createRef.current?.close();
      toast.show("Expense added", "success");
      load();
    } catch (e: any) {
      toast.show(e.message || "Could not save", "error");
    } finally {
      setSaving(false);
    }
  };

  const remove = async (id: string) => {
    try {
      await api.deleteExpense(id);
      toast.show("Deleted", "success");
      load();
    } catch (e: any) {
      toast.show(e.message, "error");
    }
  };

  return (
    <View style={{ flex: 1, backgroundColor: colors.surface }}>
      <View style={{ paddingTop: insets.top + spacing.sm, paddingHorizontal: spacing.lg, paddingBottom: spacing.md, backgroundColor: colors.surface, borderBottomWidth: 1, borderBottomColor: colors.border }}>
        <View style={{ flexDirection: "row", justifyContent: "space-between", alignItems: "center" }}>
          <View>
            <AppText variant="title">Expenses</AppText>
            <AppText variant="caption">Total logged · {gbp(total)}</AppText>
          </View>
          <IconButton icon="add" onPress={openCreate} color={colors.brand} testID="expense-new-button" />
        </View>
      </View>

      {loading ? (
        <View style={{ flex: 1, alignItems: "center", justifyContent: "center" }}>
          <ActivityIndicator color={colors.brand} size="large" />
        </View>
      ) : (
        <SectionList
          sections={sections}
          keyExtractor={(i) => i.id}
          stickySectionHeadersEnabled={false}
          contentContainerStyle={{ padding: spacing.lg, paddingBottom: 140, gap: spacing.sm, flexGrow: 1 }}
          showsVerticalScrollIndicator={false}
          ListEmptyComponent={
            <View style={{ flex: 1, justifyContent: "center", minHeight: 400 }}>
              <EmptyState icon="receipt-outline" title="No expenses yet" subtitle="Log costs like software, supervision or insurance to lower your tax." testID="expenses-empty" />
              <View style={{ paddingHorizontal: spacing.xl }}>
                <PrimaryButton title="Add expense" icon="add" onPress={openCreate} variant="secondary" testID="expenses-empty-create" />
              </View>
            </View>
          }
          renderSectionHeader={({ section }) => (
            <AppText variant="label" style={{ marginTop: spacing.md, marginBottom: spacing.xs }}>
              {section.title ? prettyMonth(section.title) : "Undated"}
            </AppText>
          )}
          renderItem={({ item }) => (
            <Card style={{ paddingVertical: spacing.md }} testID={`expense-row-${item.id}`}>
              <View style={{ flexDirection: "row", alignItems: "center", gap: spacing.md }}>
                <View style={{ width: 40, height: 40, borderRadius: 12, backgroundColor: colors.brandTertiary, alignItems: "center", justifyContent: "center" }}>
                  <Ionicons name={catIcon(item.category) as any} size={20} color={colors.brand} />
                </View>
                <View style={{ flex: 1 }}>
                  <AppText variant="body" style={{ fontWeight: "600" }}>{item.category}</AppText>
                  <AppText variant="caption">{item.description || prettyDate(item.date)}</AppText>
                </View>
                <AppText variant="heading">{gbp(item.amount)}</AppText>
                <Pressable onPress={() => remove(item.id)} hitSlop={8} testID={`expense-delete-${item.id}`}>
                  <Ionicons name="close-circle" size={22} color={colors.onSurfaceTertiary} />
                </Pressable>
              </View>
            </Card>
          )}
        />
      )}

      <AppSheet ref={createRef} snapPoints={["80%"]}>
        <AppText variant="title">Add expense</AppText>

        <AppText variant="label">Category</AppText>
        <View style={{ flexDirection: "row", flexWrap: "wrap", gap: spacing.sm }}>
          {CATEGORIES.map((c) => {
            const active = category === c.key;
            return (
              <Pressable
                key={c.key}
                testID={`expense-cat-${c.key}`}
                onPress={() => setCategory(c.key)}
                style={{ flexDirection: "row", alignItems: "center", gap: 6, paddingHorizontal: spacing.md, paddingVertical: spacing.sm, borderRadius: 999, backgroundColor: active ? colors.brandPrimary : colors.surfaceTertiary, borderWidth: 1, borderColor: active ? colors.brandPrimary : colors.border }}
              >
                <Ionicons name={c.icon as any} size={15} color={active ? colors.onBrandPrimary : colors.onSurfaceTertiary} />
                <AppText variant="caption" color={active ? colors.onBrandPrimary : colors.onSurface} style={{ fontWeight: "600" }}>{c.key}</AppText>
              </Pressable>
            );
          })}
        </View>

        <Field label="Amount (£)" value={amount} onChangeText={setAmount} placeholder="0.00" keyboardType="decimal-pad" testID="expense-amount-input" />
        <Field label="Description (optional)" value={description} onChangeText={setDescription} placeholder="e.g. Zoom subscription" testID="expense-description-input" />

        <AppText variant="label">Date</AppText>
        <Pressable
          onPress={() => setShowPicker(true)}
          style={{ backgroundColor: colors.surfaceTertiary, borderRadius: 12, paddingHorizontal: spacing.md, paddingVertical: spacing.md + 2, borderWidth: 1, borderColor: colors.border, minHeight: 52, justifyContent: "center" }}
          testID="expense-date-button"
        >
          <AppText variant="body">{prettyDate(toISODate(date))}</AppText>
        </Pressable>
        {showPicker && (
          <DateTimePicker
            value={date}
            mode="date"
            display={Platform.OS === "ios" ? "inline" : "default"}
            onChange={(e, d) => {
              if (Platform.OS !== "ios") setShowPicker(false);
              if (e.type === "dismissed") return;
              if (d) setDate(d);
            }}
          />
        )}
        {Platform.OS === "ios" && showPicker && (
          <PrimaryButton title="Done" variant="outline" onPress={() => setShowPicker(false)} testID="expense-date-done" />
        )}

        <PrimaryButton title="Save expense" onPress={save} loading={saving} variant="secondary" testID="expense-save-button" />
      </AppSheet>
    </View>
  );
}
