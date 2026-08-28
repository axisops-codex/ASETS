import React, { useCallback, useMemo, useState, useRef } from "react";
import { View, ScrollView, Pressable, ActivityIndicator, Platform } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { useFocusEffect } from "expo-router";
import { Ionicons } from "@expo/vector-icons";
import DateTimePicker from "@react-native-community/datetimepicker";
import BottomSheet from "@gorhom/bottom-sheet";
import * as Clipboard from "expo-clipboard";
import * as Haptics from "expo-haptics";
import { useTheme } from "@/src/theme/ThemeProvider";
import { useAuth } from "@/src/context/AuthContext";
import { api } from "@/src/api/client";
import { useToast } from "@/src/components/Toast";
import { AppSheet } from "@/src/components/AppSheet";
import { AppText, Card, PrimaryButton, Divider } from "@/src/components/ui";
import { gbp, fiscalYearByStartYear, fiscalYearRange, prettyDate, toISODate } from "@/src/utils/format";
import { shareTaxPdf, taxReportText } from "@/src/utils/pdf";
import { shareCsv } from "@/src/utils/csv";

export default function TaxScreen() {
  const { colors, spacing, radius } = useTheme();
  const insets = useSafeAreaInsets();
  const { user } = useAuth();
  const toast = useToast();

  const thisFy = fiscalYearRange();
  const thisStartYear = parseInt(thisFy.start.slice(0, 4), 10);

  const presets = useMemo(
    () => [
      fiscalYearByStartYear(thisStartYear),
      fiscalYearByStartYear(thisStartYear - 1),
      fiscalYearByStartYear(thisStartYear - 2),
    ],
    [thisStartYear]
  );

  const [range, setRange] = useState<{ start: string; end: string; label: string }>(presets[0]);
  const [custom, setCustom] = useState(false);
  const [summary, setSummary] = useState<any>(null);
  const [loading, setLoading] = useState(true);

  const customRef = useRef<BottomSheet>(null);
  const [cStart, setCStart] = useState(new Date(presets[0].start));
  const [cEnd, setCEnd] = useState(new Date(presets[0].end));
  const [picker, setPicker] = useState<null | "start" | "end">(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      setSummary(await api.summary(range.start, range.end));
    } catch (e: any) {
      toast.show(e.message || "Could not calculate", "error");
    } finally {
      setLoading(false);
    }
  }, [range.start, range.end]);

  useFocusEffect(useCallback(() => { load(); }, [load]));

  const tax = summary?.tax;

  const applyCustom = () => {
    const s = toISODate(cStart);
    const e = toISODate(cEnd);
    if (s > e) return toast.show("Start must be before end", "error");
    setRange({ start: s, end: e, label: `${prettyDate(s)} – ${prettyDate(e)}` });
    setCustom(true);
    customRef.current?.close();
  };

  const copyText = async () => {
    if (!tax) return;
    await Clipboard.setStringAsync(taxReportText(tax, range.label));
    Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success).catch(() => {});
    toast.show("Copied — paste into HMRC", "success");
  };

  const exportPdf = async () => {
    if (!tax) return;
    try {
      await shareTaxPdf(tax, range.label, user as any);
    } catch (e: any) {
      toast.show(e.message || "Could not export", "error");
    }
  };

  const [exportingCsv, setExportingCsv] = useState(false);
  const exportCsv = async () => {
    setExportingCsv(true);
    try {
      const res = await api.exportCsv(range.start, range.end);
      await shareCsv(res.csv, res.filename);
    } catch (e: any) {
      toast.show(e.message || "Could not export CSV", "error");
    } finally {
      setExportingCsv(false);
    }
  };

  return (
    <View style={{ flex: 1, backgroundColor: colors.surface }}>
      <View style={{ paddingTop: insets.top + spacing.sm, paddingHorizontal: spacing.lg, paddingBottom: spacing.md, backgroundColor: colors.surface }}>
        <AppText variant="title">Tax estimate</AppText>
        <AppText variant="caption">Plain numbers for your Self Assessment</AppText>
      </View>

      {/* Period selector chips (horizontal, chrome) */}
      <View style={{ height: 56, justifyContent: "center" }}>
        <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ paddingHorizontal: spacing.lg, gap: spacing.sm, alignItems: "center" }}>
          {presets.map((p) => {
            const active = !custom && range.start === p.start;
            return (
              <Chip key={p.start} label={p.label} active={active} onPress={() => { setCustom(false); setRange(p); }} testID={`tax-fy-${p.start.slice(0, 4)}`} />
            );
          })}
          <Chip label={custom ? range.label : "Custom range"} icon="calendar-outline" active={custom} onPress={() => customRef.current?.expand()} testID="tax-custom-range" />
        </ScrollView>
      </View>

      {loading ? (
        <View style={{ flex: 1, alignItems: "center", justifyContent: "center" }}>
          <ActivityIndicator color={colors.brand} size="large" />
        </View>
      ) : (
        <ScrollView contentContainerStyle={{ padding: spacing.lg, paddingTop: spacing.sm, paddingBottom: 140, gap: spacing.lg }} showsVerticalScrollIndicator={false}>
          {/* Receipt canvas */}
          <Card testID="tax-canvas" style={{ padding: spacing.xl }}>
            <View style={{ alignItems: "center", marginBottom: spacing.lg }}>
              <View style={{ width: 48, height: 48, borderRadius: 14, backgroundColor: colors.brandTertiary, alignItems: "center", justifyContent: "center", marginBottom: spacing.sm }}>
                <Ionicons name="calculator" size={24} color={colors.brand} />
              </View>
              <AppText variant="caption">HMRC Self Assessment</AppText>
              <AppText variant="heading">{range.label}</AppText>
            </View>

            <ReceiptRow label="Total sales" value={gbp(tax?.sales ?? 0)} />
            <ReceiptRow label="Less allowable expenses" value={`- ${gbp(tax?.expenses ?? 0)}`} />
            <View style={{ height: 1, backgroundColor: colors.borderStrong, marginVertical: spacing.sm }} />
            <ReceiptRow label="Taxable profit" value={gbp(tax?.profit ?? 0)} strong />

            <View style={{ marginTop: spacing.md, backgroundColor: colors.surfaceTertiary, borderRadius: radius.md, padding: spacing.md, gap: 4 }}>
              <ReceiptRow label="Personal allowance" value={gbp(tax?.personal_allowance ?? 0)} small />
              <ReceiptRow label="Income taxed" value={gbp(tax?.taxable_income ?? 0)} small />
              {tax?.bands?.map((b: any, i: number) => (
                <ReceiptRow key={i} label={`  ${b.label}`} value={gbp(b.tax)} small muted />
              ))}
            </View>

            <View style={{ marginTop: spacing.md }}>
              <ReceiptRow label="Income Tax" value={gbp(tax?.income_tax ?? 0)} />
              <ReceiptRow label="National Insurance (Class 4)" value={gbp(tax?.national_insurance ?? 0)} />
            </View>

            <Divider />
            <View style={{ backgroundColor: colors.brandPrimary, borderRadius: radius.md, padding: spacing.lg, gap: 4 }}>
              <AppText variant="label" color={colors.onBrandPrimary} style={{ opacity: 0.9 }}>Tax to set aside</AppText>
              <AppText variant="mono" color={colors.onBrandPrimary} testID="tax-total-due">{gbp(tax?.total_due ?? 0)}</AppText>
            </View>
            <View style={{ flexDirection: "row", justifyContent: "space-between", marginTop: spacing.md }}>
              <AppText variant="body" color={colors.onSurfaceTertiary}>Estimated take home</AppText>
              <AppText variant="heading" color={colors.success}>{gbp(tax?.take_home ?? 0)}</AppText>
            </View>

            <AppText variant="caption" style={{ marginTop: spacing.lg, textAlign: "center" }}>
              Estimate based on 2024/25 England &amp; NI rates. No VAT (exempt healthcare). Not financial advice.
            </AppText>
          </Card>

          <View style={{ gap: spacing.md }}>
            <PrimaryButton title="Download PDF" icon="download-outline" onPress={exportPdf} testID="tax-export-pdf" />
            <PrimaryButton title="Copy figures" icon="copy-outline" variant="outline" onPress={copyText} testID="tax-copy-text" />
            <PrimaryButton title="Export CSV for accountant" icon="grid-outline" variant="outline" onPress={exportCsv} loading={exportingCsv} testID="tax-export-csv" />
          </View>
        </ScrollView>
      )}

      {/* Custom range sheet */}
      <AppSheet ref={customRef} snapPoints={["70%"]}>
        <AppText variant="title">Custom range</AppText>
        <AppText variant="label">Start date</AppText>
        <Pressable onPress={() => setPicker("start")} style={dateBtn(colors, spacing, radius)} testID="tax-custom-start">
          <AppText variant="body">{prettyDate(toISODate(cStart))}</AppText>
        </Pressable>
        <AppText variant="label">End date</AppText>
        <Pressable onPress={() => setPicker("end")} style={dateBtn(colors, spacing, radius)} testID="tax-custom-end">
          <AppText variant="body">{prettyDate(toISODate(cEnd))}</AppText>
        </Pressable>
        {picker && (
          <DateTimePicker
            value={picker === "start" ? cStart : cEnd}
            mode="date"
            display={Platform.OS === "ios" ? "inline" : "default"}
            onChange={(e, d) => {
              if (Platform.OS !== "ios") setPicker(null);
              if (e.type === "dismissed") return;
              if (d) picker === "start" ? setCStart(d) : setCEnd(d);
            }}
          />
        )}
        {Platform.OS === "ios" && picker && (
          <PrimaryButton title="Done" variant="outline" onPress={() => setPicker(null)} testID="tax-date-done" />
        )}
        <PrimaryButton title="Apply range" onPress={applyCustom} testID="tax-apply-custom" />
      </AppSheet>
    </View>
  );
}

function dateBtn(colors: any, spacing: any, radius: any) {
  return { backgroundColor: colors.surfaceTertiary, borderRadius: radius.md, paddingHorizontal: spacing.md, paddingVertical: spacing.md + 2, borderWidth: 1, borderColor: colors.border, minHeight: 52, justifyContent: "center" as const };
}

function Chip({ label, active, onPress, icon, testID }: any) {
  const { colors, spacing } = useTheme();
  return (
    <Pressable
      testID={testID}
      onPress={onPress}
      style={{ flexShrink: 0, height: 36, flexDirection: "row", alignItems: "center", gap: 6, paddingHorizontal: spacing.md, borderRadius: 999, backgroundColor: active ? colors.brandPrimary : colors.surfaceTertiary, borderWidth: 1, borderColor: active ? colors.brandPrimary : colors.border }}
    >
      {icon && <Ionicons name={icon} size={14} color={active ? colors.onBrandPrimary : colors.onSurfaceTertiary} />}
      <AppText variant="caption" color={active ? colors.onBrandPrimary : colors.onSurface} style={{ fontWeight: "700" }}>{label}</AppText>
    </Pressable>
  );
}

function ReceiptRow({ label, value, strong, small, muted }: any) {
  const { colors } = useTheme();
  return (
    <View style={{ flexDirection: "row", justifyContent: "space-between", alignItems: "center", paddingVertical: small ? 3 : 7 }}>
      <AppText variant={small ? "caption" : "body"} color={muted ? colors.onSurfaceTertiary : colors.onSurface} style={strong ? { fontWeight: "700" } : undefined}>
        {label}
      </AppText>
      <AppText variant={small ? "caption" : "body"} color={muted ? colors.onSurfaceTertiary : colors.onSurface} style={{ fontWeight: strong ? "700" : "600" }}>
        {value}
      </AppText>
    </View>
  );
}
