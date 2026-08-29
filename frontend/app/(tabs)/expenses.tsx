import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { View, SectionList, Pressable, ActivityIndicator, Platform, Linking } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { useFocusEffect, useLocalSearchParams, useRouter } from "expo-router";
import { Ionicons } from "@expo/vector-icons";
import DateTimePicker from "@react-native-community/datetimepicker";
import BottomSheet from "@gorhom/bottom-sheet";
import * as Haptics from "expo-haptics";
import * as ImagePicker from "expo-image-picker";
import { Image } from "expo-image";
import { useTheme } from "@/src/theme/ThemeProvider";
import { useTabBarHeight } from "@/src/hooks/use-tab-bar-height";
import { api, receiptUrl } from "@/src/api/client";
import { useToast } from "@/src/components/Toast";
import { AppSheet } from "@/src/components/AppSheet";
import { AppText, Card, Field, PrimaryButton, EmptyState, IconButton } from "@/src/components/ui";
import { gbp, prettyDate, prettyMonth, toISODate } from "@/src/utils/format";

type Category = {
  code: string;
  label: string;
  icon: string;
  hint: string;
  hmrc_field: string;
  disallowable: boolean;
};

// Categories come from the API, which reads them from the database. They
// used to be hardcoded here as well as in the backend and in the HMRC
// mapping — three lists that drifted, which is how a client dinner ended
// up claimed as an allowable expense.
const FALLBACK: Category[] = [
  { code: "Other", label: "Other", icon: "pricetag-outline", hint: "", hmrc_field: "otherExpenses", disallowable: false },
];

export default function Expenses() {
  const { colors, spacing } = useTheme();
  const tabBarHeight = useTabBarHeight();
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const params = useLocalSearchParams<{ new?: string }>();
  const [cats, setCats] = useState<Category[]>(FALLBACK);
  const catIcon = (code: string) =>
    cats.find((c) => c.code === code)?.icon || "pricetag-outline";
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
  const [scanning, setScanning] = useState(false);
  const [receiptPath, setReceiptPath] = useState<string | null>(null);
  const [receiptPreview, setReceiptPreview] = useState<string | null>(null);
  const [permBlocked, setPermBlocked] = useState(false);
  const [thumbs, setThumbs] = useState<Record<string, string>>({});

  const load = useCallback(async () => {
    try {
      const list = await api.expenses();
      setExpenses(list);
      const withReceipts = list.filter((e: any) => e.receipt_path);
      if (withReceipts.length) {
        const entries = await Promise.all(
          withReceipts.map(async (e: any) => [e.id, await receiptUrl(e.receipt_path)] as [string, string])
        );
        setThumbs(Object.fromEntries(entries));
      }
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
    setReceiptPath(null);
    setReceiptPreview(null);
    setPermBlocked(false);
    createRef.current?.expand();
  };

  const pickAndScan = async (fromCamera: boolean) => {
    setPermBlocked(false);
    try {
      const perm = fromCamera
        ? await ImagePicker.getCameraPermissionsAsync()
        : await ImagePicker.getMediaLibraryPermissionsAsync();
      let granted = perm.granted;
      if (!granted) {
        if (perm.canAskAgain) {
          const req = fromCamera
            ? await ImagePicker.requestCameraPermissionsAsync()
            : await ImagePicker.requestMediaLibraryPermissionsAsync();
          granted = req.granted;
          if (!granted && !req.canAskAgain) setPermBlocked(true);
        } else {
          setPermBlocked(true);
        }
      }
      if (!granted) {
        toast.show(fromCamera ? "Camera access needed to scan receipts" : "Photo access needed", "info");
        return;
      }
      const result = fromCamera
        ? await ImagePicker.launchCameraAsync({ mediaTypes: ["images"], quality: 0.5, base64: true })
        : await ImagePicker.launchImageLibraryAsync({ mediaTypes: ["images"], quality: 0.5, base64: true });
      if (result.canceled || !result.assets?.[0]?.base64) return;
      const asset = result.assets[0];
      setReceiptPreview(asset.uri);
      setScanning(true);
      const res = await api.scanReceipt(asset.base64!);
      if (res.category) setCategory(res.category);
      if (res.amount) setAmount(String(res.amount));
      setDescription(res.description || res.merchant || "");
      if (res.date) {
        const d = new Date(res.date);
        if (!isNaN(d.getTime())) setDate(d);
      }
      setReceiptPath(res.receipt_path || null);
      Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success).catch(() => {});
      toast.show("Receipt read — check the details", "success");
    } catch (e: any) {
      toast.show(e.message || "Could not read the receipt", "error");
    } finally {
      setScanning(false);
    }
  };

  const save = async () => {
    const amt = parseFloat(amount || "0");
    if (!amt || amt <= 0) return toast.show("Enter an amount", "error");
    setSaving(true);
    try {
      await api.createExpense({ category, description, amount: amt, date: toISODate(date), receipt_path: receiptPath });
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
          contentContainerStyle={{ padding: spacing.lg, paddingBottom: tabBarHeight + spacing.lg, gap: spacing.sm, flexGrow: 1 }}
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
                {thumbs[item.id] ? (
                  <Image source={{ uri: thumbs[item.id] }} style={{ width: 40, height: 40, borderRadius: 12 }} contentFit="cover" testID={`expense-thumb-${item.id}`} />
                ) : (
                  <View style={{ width: 40, height: 40, borderRadius: 12, backgroundColor: colors.brandTertiary, alignItems: "center", justifyContent: "center" }}>
                    <Ionicons name={catIcon(item.category) as any} size={20} color={colors.brand} />
                  </View>
                )}
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

      <AppSheet ref={createRef} snapPoints={["88%"]}>
        <AppText variant="title">Add expense</AppText>

        {/* Scan receipt (AI) */}
        <View style={{ backgroundColor: colors.brandTertiary, borderRadius: 16, padding: spacing.md, gap: spacing.sm }}>
          <View style={{ flexDirection: "row", alignItems: "center", gap: spacing.sm }}>
            <Ionicons name="sparkles" size={18} color={colors.brand} />
            <AppText variant="body" color={colors.onBrandTertiary} style={{ fontWeight: "700", flex: 1 }}>Scan a receipt</AppText>
            {scanning && <ActivityIndicator color={colors.brand} />}
          </View>
          <AppText variant="caption" color={colors.onBrandTertiary}>Snap or pick a photo and we'll fill in the details for you.</AppText>
          {receiptPreview ? (
            <View style={{ flexDirection: "row", alignItems: "center", gap: spacing.md, marginTop: 4 }}>
              <Image source={{ uri: receiptPreview }} style={{ width: 54, height: 54, borderRadius: 10 }} contentFit="cover" />
              <Pressable onPress={() => pickAndScan(true)} testID="expense-rescan"><AppText variant="body" color={colors.brand} style={{ fontWeight: "600" }}>Rescan</AppText></Pressable>
            </View>
          ) : (
            <View style={{ flexDirection: "row", gap: spacing.sm, marginTop: 4 }}>
              <View style={{ flex: 1 }}>
                <PrimaryButton title="Take photo" icon="camera-outline" onPress={() => pickAndScan(true)} loading={scanning} testID="expense-scan-camera" />
              </View>
              <View style={{ flex: 1 }}>
                <PrimaryButton title="Gallery" icon="images-outline" variant="outline" onPress={() => pickAndScan(false)} testID="expense-scan-gallery" />
              </View>
            </View>
          )}
          {permBlocked && (
            <Pressable onPress={() => Linking.openSettings()} testID="expense-open-settings" style={{ paddingTop: 4 }}>
              <AppText variant="caption" color={colors.brand} style={{ fontWeight: "700" }}>Open Settings to allow access</AppText>
            </Pressable>
          )}
        </View>

        <AppText variant="label">Category</AppText>
        <View style={{ flexDirection: "row", flexWrap: "wrap", gap: spacing.sm }}>
          {cats.map((c) => {
            const active = category === c.code;
            return (
              <Pressable
                key={c.code}
                testID={`expense-cat-${c.code}`}
                onPress={() => setCategory(c.code)}
                style={{ flexDirection: "row", alignItems: "center", gap: 6, paddingHorizontal: spacing.md, paddingVertical: spacing.sm, borderRadius: 999, backgroundColor: active ? colors.brandPrimary : colors.surfaceTertiary, borderWidth: 1, borderColor: active ? colors.brandPrimary : colors.border }}
              >
                <Ionicons name={c.icon as any} size={15} color={active ? colors.onBrandPrimary : colors.onSurfaceTertiary} />
                <AppText variant="caption" color={active ? colors.onBrandPrimary : colors.onSurface} style={{ fontWeight: "600" }}>{c.label}</AppText>
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
