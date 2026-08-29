import React, { useCallback, useEffect, useState } from "react";
import { View, ScrollView, Pressable, ActivityIndicator } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { useRouter } from "expo-router";
import { Ionicons } from "@expo/vector-icons";
import * as WebBrowser from "expo-web-browser";
import { useTheme } from "@/src/theme/ThemeProvider";
import { hmrc } from "@/src/api/client";
import { useToast } from "@/src/components/Toast";
import { AppText, Card, Field, PrimaryButton, IconButton, Pill, Divider } from "@/src/components/ui";
import { gbp } from "@/src/utils/format";

type Status = {
  configured: boolean;
  connected: boolean;
  environment?: string;
  nino_set?: boolean;
  business_id?: string | null;
  tax_year?: string;
  quarters?: { quarter: number; period_start: string; period_end: string; due_date: string }[];
  current_quarter?: { quarter: number } | null;
  missing_fraud_headers?: string[];
  last_error?: string | null;
};

const shortDate = (iso: string) =>
  new Date(iso).toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric" });

export default function Hmrc() {
  const { colors, spacing } = useTheme();
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const toast = useToast();

  const [status, setStatus] = useState<Status | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [nino, setNino] = useState("");
  const [businesses, setBusinesses] = useState<any[] | null>(null);
  const [preview, setPreview] = useState<any | null>(null);
  const [submissions, setSubmissions] = useState<any[]>([]);

  const refresh = useCallback(async () => {
    try {
      const next = await hmrc.status();
      setStatus(next);
      if (next.connected) {
        hmrc.submissions().then((r: any) => setSubmissions(r.submissions || [])).catch(() => {});
      }
    } catch (e: any) {
      toast.show(e.message, "error");
    } finally {
      setLoading(false);
    }
  }, [toast]);

  useEffect(() => { refresh(); }, [refresh]);

  const connect = async () => {
    setBusy(true);
    try {
      const { authorization_url } = await hmrc.connect();
      // HMRC signs the user in, then redirects to the API, which bounces
      // back to this app via the asets:// scheme.
      const result = await WebBrowser.openAuthSessionAsync(authorization_url, "asets://hmrc");
      if (result.type === "success" && result.url.includes("status=connected")) {
        toast.show("Connected to HMRC", "success");
      } else if (result.type === "success") {
        toast.show(decodeURIComponent(result.url.split("reason=")[1] || "Could not connect"), "error");
      }
      await refresh();
    } catch (e: any) {
      toast.show(e.message, "error");
    } finally {
      setBusy(false);
    }
  };

  const saveNino = async () => {
    setBusy(true);
    try {
      await hmrc.setNino(nino.trim().toUpperCase());
      toast.show("National Insurance number saved", "success");
      setNino("");
      await refresh();
      await loadBusinesses();
    } catch (e: any) {
      toast.show(e.message, "error");
    } finally {
      setBusy(false);
    }
  };

  const loadBusinesses = async () => {
    setBusy(true);
    try {
      const result = await hmrc.businesses();
      setBusinesses(result.businesses || []);
      if ((result.businesses || []).length === 0) {
        toast.show("HMRC has no self-employment business on this record", "error");
      }
    } catch (e: any) {
      toast.show(e.message, "error");
    } finally {
      setBusy(false);
    }
  };

  const chooseBusiness = async (businessId: string) => {
    setBusy(true);
    try {
      await hmrc.setBusiness(businessId);
      setBusinesses(null);
      await refresh();
    } catch (e: any) {
      toast.show(e.message, "error");
    } finally {
      setBusy(false);
    }
  };

  const openPreview = async (quarter: number) => {
    setBusy(true);
    try {
      setPreview(await hmrc.quarterPreview(status!.tax_year!, quarter));
    } catch (e: any) {
      toast.show(e.message, "error");
    } finally {
      setBusy(false);
    }
  };

  const submit = async () => {
    setBusy(true);
    try {
      await hmrc.submitQuarter(status!.tax_year!, preview.quarter.quarter);
      toast.show("Sent to HMRC", "success");
      setPreview(null);
      await refresh();
    } catch (e: any) {
      toast.show(e.message, "error");
    } finally {
      setBusy(false);
    }
  };

  const disconnect = async () => {
    setBusy(true);
    try {
      await hmrc.disconnect();
      setBusinesses(null);
      setPreview(null);
      await refresh();
      toast.show("Disconnected from HMRC", "success");
    } catch (e: any) {
      toast.show(e.message, "error");
    } finally {
      setBusy(false);
    }
  };

  if (loading) {
    return (
      <View style={{ flex: 1, backgroundColor: colors.surface, alignItems: "center", justifyContent: "center" }}>
        <ActivityIndicator color={colors.brand} />
      </View>
    );
  }

  return (
    <View style={{ flex: 1, backgroundColor: colors.surface }}>
      <View style={{ paddingTop: insets.top + spacing.sm, paddingHorizontal: spacing.lg,
                     paddingBottom: spacing.sm, flexDirection: "row", alignItems: "center", gap: spacing.md }}>
        <IconButton icon="chevron-back" onPress={() => router.back()} testID="hmrc-back" />
        <AppText variant="title">HMRC</AppText>
      </View>

      <ScrollView contentContainerStyle={{ padding: spacing.lg, paddingBottom: insets.bottom + 60, gap: spacing.xl }}>
        {!status?.configured ? (
          <Card style={{ gap: spacing.sm }}>
            <AppText variant="body" style={{ fontWeight: "700" }}>Not available yet</AppText>
            <AppText variant="caption">
              Filing to HMRC isn&apos;t switched on for this app yet. Your tax estimate keeps working as normal.
            </AppText>
          </Card>
        ) : !status.connected ? (
          <View style={{ gap: spacing.sm }}>
            <Card style={{ gap: spacing.md }}>
              <AppText variant="body" style={{ fontWeight: "700" }}>Connect ASETS to HMRC</AppText>
              <AppText variant="caption">
                You&apos;ll sign in with your Government Gateway details on HMRC&apos;s own website. ASETS never
                sees your password. You can disconnect at any time.
              </AppText>
              {status.environment === "sandbox" ? (
                <Pill label="Sandbox — test data only" tone="warning" testID="hmrc-sandbox-pill" />
              ) : null}
              <PrimaryButton title="Connect to HMRC" icon="link-outline" loading={busy}
                             onPress={connect} testID="hmrc-connect" />
            </Card>
          </View>
        ) : (
          <>
            <Card style={{ gap: spacing.sm }}>
              <View style={{ flexDirection: "row", alignItems: "center", gap: spacing.sm }}>
                <Ionicons name="checkmark-circle" size={20} color={colors.success} />
                <AppText variant="body" style={{ flex: 1, fontWeight: "700" }}>Connected to HMRC</AppText>
                {status.environment === "sandbox" ? <Pill label="Sandbox" tone="warning" /> : null}
              </View>
              <AppText variant="caption">Tax year {status.tax_year}</AppText>
              {status.last_error ? (
                <AppText variant="caption" color={colors.error}>{status.last_error}</AppText>
              ) : null}
              {status.missing_fraud_headers?.length ? (
                <AppText variant="caption" color={colors.warning}>
                  Some device details could not be read, which HMRC may reject:
                  {" " + status.missing_fraud_headers.join(", ")}
                </AppText>
              ) : null}
            </Card>

            {!status.nino_set ? (
              <View style={{ gap: spacing.sm }}>
                <AppText variant="label">Your National Insurance number</AppText>
                <Card style={{ gap: spacing.md }}>
                  <AppText variant="caption">
                    HMRC identifies your records by NI number. It is stored encrypted and only used to talk to HMRC.
                  </AppText>
                  <Field label="NI number" value={nino} onChangeText={setNino}
                         placeholder="QQ123456C" autoCapitalize="characters" testID="hmrc-nino-input" />
                  <PrimaryButton title="Save and find my business" loading={busy}
                                 onPress={saveNino} testID="hmrc-nino-save" />
                </Card>
              </View>
            ) : !status.business_id ? (
              <View style={{ gap: spacing.sm }}>
                <AppText variant="label">Choose your business</AppText>
                <Card style={{ gap: spacing.md }}>
                  {businesses === null ? (
                    <PrimaryButton title="Find my business at HMRC" loading={busy}
                                   onPress={loadBusinesses} testID="hmrc-find-business" />
                  ) : (
                    businesses.map((b) => (
                      <Pressable key={b.businessId} testID={`hmrc-business-${b.businessId}`}
                                 onPress={() => chooseBusiness(b.businessId)}
                                 style={{ flexDirection: "row", alignItems: "center", gap: spacing.md,
                                          paddingVertical: spacing.sm }}>
                        <Ionicons name="briefcase-outline" size={20} color={colors.onSurfaceTertiary} />
                        <View style={{ flex: 1 }}>
                          <AppText variant="body">{b.tradingName || "Self-employment"}</AppText>
                          <AppText variant="caption">{b.businessId}</AppText>
                        </View>
                        <Ionicons name="chevron-forward" size={18} color={colors.onSurfaceTertiary} />
                      </Pressable>
                    ))
                  )}
                </Card>
              </View>
            ) : (
              <View style={{ gap: spacing.sm }}>
                <AppText variant="label">Quarterly updates — {status.tax_year}</AppText>
                <Card style={{ gap: spacing.md }}>
                  <AppText variant="caption">
                    Each update reports everything from 6 April to the end of that quarter, so a later update
                    replaces an earlier one.
                  </AppText>
                  {status.quarters?.map((q) => (
                    <View key={q.quarter}>
                      <Pressable testID={`hmrc-quarter-${q.quarter}`} onPress={() => openPreview(q.quarter)}
                                 style={{ flexDirection: "row", alignItems: "center", gap: spacing.md,
                                          paddingVertical: spacing.sm }}>
                        <View style={{ flex: 1 }}>
                          <AppText variant="body">Quarter {q.quarter}</AppText>
                          <AppText variant="caption">
                            to {shortDate(q.period_end)} · due {shortDate(q.due_date)}
                          </AppText>
                        </View>
                        {status.current_quarter?.quarter === q.quarter ? <Pill label="Now" tone="info" /> : null}
                        <Ionicons name="chevron-forward" size={18} color={colors.onSurfaceTertiary} />
                      </Pressable>
                      <Divider />
                    </View>
                  ))}
                </Card>
              </View>
            )}

            {preview ? (
              <View style={{ gap: spacing.sm }}>
                <AppText variant="label">Check before sending</AppText>
                <Card style={{ gap: spacing.md, borderColor: colors.brand }}>
                  <AppText variant="caption">
                    {shortDate(preview.summary.period_start)} to {shortDate(preview.summary.period_end)}
                  </AppText>
                  <Row label="Income" value={gbp(preview.summary.turnover)} />
                  <Row label="Expenses" value={gbp(preview.summary.expenses_total)} />
                  <Divider />
                  <Row label="Profit" value={gbp(preview.summary.profit)} strong />
                  <AppText variant="caption">
                    These are the figures ASETS will declare to HMRC. Check them against your records — you are
                    responsible for what is submitted.
                  </AppText>
                  <PrimaryButton title="Send to HMRC" icon="cloud-upload-outline" loading={busy}
                                 onPress={submit} testID="hmrc-submit" />
                  <PrimaryButton title="Cancel" variant="outline" onPress={() => setPreview(null)}
                                 testID="hmrc-cancel-preview" />
                </Card>
              </View>
            ) : null}

            {submissions.length ? (
              <View style={{ gap: spacing.sm }}>
                <AppText variant="label">What ASETS has sent</AppText>
                <Card style={{ gap: spacing.md }}>
                  {submissions.slice(0, 8).map((s) => (
                    <View key={s.id} style={{ flexDirection: "row", alignItems: "center", gap: spacing.sm }}>
                      <View style={{ flex: 1 }}>
                        <AppText variant="body">{s.type.replace(/_/g, " ")}</AppText>
                        <AppText variant="caption">
                          {new Date(s.created_at).toLocaleString("en-GB")}
                          {s.period_end ? ` · to ${shortDate(s.period_end)}` : ""}
                        </AppText>
                      </View>
                      <Pill label={s.status}
                            tone={s.status === "accepted" ? "success" : s.status === "pending" ? "info" : "warning"} />
                    </View>
                  ))}
                </Card>
              </View>
            ) : null}

            <PrimaryButton title="Disconnect from HMRC" variant="outline" loading={busy}
                           onPress={disconnect} testID="hmrc-disconnect" />
          </>
        )}
      </ScrollView>
    </View>
  );
}

function Row({ label, value, strong }: { label: string; value: string; strong?: boolean }) {
  return (
    <View style={{ flexDirection: "row", justifyContent: "space-between" }}>
      <AppText variant="body">{label}</AppText>
      <AppText variant="body" style={{ fontWeight: strong ? "800" : "600" }}>{value}</AppText>
    </View>
  );
}
