import React, { useCallback, useMemo, useRef, useState, useEffect } from "react";
import { View, FlatList, Pressable, ActivityIndicator, Platform, Modal, TextInput } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { useFocusEffect, useLocalSearchParams, useRouter } from "expo-router";
import { Ionicons } from "@expo/vector-icons";
import DateTimePicker from "@react-native-community/datetimepicker";
import BottomSheet from "@gorhom/bottom-sheet";
import * as Haptics from "expo-haptics";
import { useTheme } from "@/src/theme/ThemeProvider";
import { useTabBarHeight } from "@/src/hooks/use-tab-bar-height";
import { useAuth } from "@/src/context/AuthContext";
import { api } from "@/src/api/client";
import { useToast } from "@/src/components/Toast";
import { AppSheet } from "@/src/components/AppSheet";
import { AppText, Card, Field, PrimaryButton, Pill, EmptyState, IconButton, Divider } from "@/src/components/ui";
import { gbp, prettyDate, toISODate } from "@/src/utils/format";
import { shareInvoicePdf } from "@/src/utils/pdf";
import { PSYCHOLOGY_SERVICES } from "@/src/data/services";

type Item = { description: string; quantity: string; unit_price: string };

const STATUS_TONE: any = { paid: "success", sent: "info", draft: "neutral" };

export default function Invoices() {
  const { colors, spacing } = useTheme();
  const tabBarHeight = useTabBarHeight();
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const params = useLocalSearchParams<{ new?: string }>();
  const { user } = useAuth();
  const toast = useToast();

  const [invoices, setInvoices] = useState<any[]>([]);
  const [clients, setClients] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);

  const createRef = useRef<BottomSheet>(null);
  const detailRef = useRef<BottomSheet>(null);
  const [selected, setSelected] = useState<any>(null);
  const [editingId, setEditingId] = useState<string | null>(null);

  // form
  const [clientId, setClientId] = useState("");
  const [issueDate, setIssueDate] = useState(new Date());
  const [dueDate, setDueDate] = useState<Date | null>(null);
  const [items, setItems] = useState<Item[]>([{ description: "Therapy sessions", quantity: "1", unit_price: "" }]);
  const [notes, setNotes] = useState("");
  const [status, setStatus] = useState<"draft" | "sent" | "paid">("sent");
  const [saving, setSaving] = useState(false);
  const [picker, setPicker] = useState<null | "issue" | "due">(null);
  const [servicePickerFor, setServicePickerFor] = useState<number | null>(null);
  const [serviceQuery, setServiceQuery] = useState("");

  const load = useCallback(async () => {
    try {
      const [inv, cl] = await Promise.all([api.invoices(), api.clients()]);
      setInvoices(inv);
      setClients(cl);
    } catch (e: any) {
      toast.show(e.message || "Could not load invoices", "error");
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

  const outstanding = useMemo(
    () => invoices.filter((i) => i.status !== "paid").reduce((s, i) => s + (i.total || 0), 0),
    [invoices]
  );

  const resetForm = () => {
    setClientId(clients[0]?.id || "");
    setIssueDate(new Date());
    setDueDate(null);
    setItems([{ description: "Therapy sessions", quantity: "1", unit_price: "" }]);
    setNotes("");
    setStatus("sent");
  };

  const openCreate = () => {
    if (clients.length === 0) {
      toast.show("Add a client first", "info");
      router.push("/clients");
      return;
    }
    setEditingId(null);
    resetForm();
    setClientId((prev) => prev || clients[0]?.id || "");
    createRef.current?.expand();
  };

  const openEdit = (inv: any) => {
    detailRef.current?.close();
    setEditingId(inv.id);
    setClientId(inv.client_id);
    setIssueDate(inv.issue_date ? new Date(inv.issue_date) : new Date());
    setDueDate(inv.due_date ? new Date(inv.due_date) : null);
    setItems(
      inv.items?.length
        ? inv.items.map((it: any) => ({ description: it.description, quantity: String(it.quantity), unit_price: String(it.unit_price) }))
        : [{ description: "", quantity: "1", unit_price: "" }]
    );
    setNotes(inv.notes || "");
    setStatus(inv.status);
    setTimeout(() => createRef.current?.expand(), 260);
  };

  const total = items.reduce((s, it) => s + (parseFloat(it.quantity || "0") || 0) * (parseFloat(it.unit_price || "0") || 0), 0);

  const userServices: any[] = (user as any)?.services || [];
  const filteredServices = (() => {
    const fromUser = userServices.map((s: any) => ({ name: s.name, price: s.price, unit: s.unit, saved: true }));
    const names = new Set(fromUser.map((s: any) => (s.name || "").toLowerCase()));
    // keep `price` present in both branches so the picker list has one shape
    const cat = PSYCHOLOGY_SERVICES.filter((s) => !names.has(s.name.toLowerCase())).map((s) => ({ name: s.name, price: undefined as number | undefined, unit: s.unit, saved: false }));
    const list = [...fromUser, ...cat];
    const q = serviceQuery.trim().toLowerCase();
    return q ? list.filter((s) => s.name.toLowerCase().includes(q)) : list;
  })();

  const applyService = (svc: any) => {
    const idx = servicePickerFor;
    if (idx === null) return;
    setItems((p) => p.map((x, i) => (i === idx ? { ...x, description: svc.name, unit_price: svc.price != null && svc.price !== "" ? String(svc.price) : x.unit_price } : x)));
    setServicePickerFor(null);
    setServiceQuery("");
  };

  const save = async () => {
    if (!clientId) return toast.show("Choose a client", "error");
    if (total <= 0) return toast.show("Add at least one line with an amount", "error");
    setSaving(true);
    const payload = {
      client_id: clientId,
      issue_date: toISODate(issueDate),
      due_date: dueDate ? toISODate(dueDate) : null,
      items: items.map((it) => ({
        description: it.description,
        quantity: parseFloat(it.quantity || "0") || 0,
        unit_price: parseFloat(it.unit_price || "0") || 0,
      })),
      notes,
      status,
    };
    try {
      if (editingId) await api.updateInvoice(editingId, payload);
      else await api.createInvoice(payload);
      Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success).catch(() => {});
      createRef.current?.close();
      toast.show(editingId ? "Invoice updated" : "Invoice created", "success");
      setEditingId(null);
      load();
    } catch (e: any) {
      toast.show(e.message || "Could not save", "error");
    } finally {
      setSaving(false);
    }
  };

  const openDetail = (inv: any) => {
    setSelected(inv);
    detailRef.current?.expand();
  };

  const markPaid = async () => {
    if (!selected) return;
    try {
      await api.updateInvoice(selected.id, { status: "paid" });
      toast.show("Marked as paid", "success");
      detailRef.current?.close();
      load();
    } catch (e: any) {
      toast.show(e.message, "error");
    }
  };

  const removeInvoice = async () => {
    if (!selected) return;
    try {
      await api.deleteInvoice(selected.id);
      toast.show("Invoice deleted", "success");
      detailRef.current?.close();
      load();
    } catch (e: any) {
      toast.show(e.message, "error");
    }
  };

  const doShare = async () => {
    if (!selected) return;
    const client = clients.find((c) => c.id === selected.client_id) || {};
    try {
      await shareInvoicePdf(selected, user as any, client);
    } catch (e: any) {
      toast.show(e.message || "Could not create PDF", "error");
    }
  };

  return (
    <View style={{ flex: 1, backgroundColor: colors.surface }}>
      <View style={{ paddingTop: insets.top + spacing.sm, paddingHorizontal: spacing.lg, paddingBottom: spacing.md, backgroundColor: colors.surface, borderBottomWidth: 1, borderBottomColor: colors.border }}>
        <View style={{ flexDirection: "row", justifyContent: "space-between", alignItems: "center" }}>
          <View>
            <AppText variant="title">Invoices</AppText>
            <AppText variant="caption">Awaiting payment · {gbp(outstanding)}</AppText>
          </View>
          <IconButton icon="add" onPress={openCreate} color={colors.brand} testID="invoice-new-button" />
        </View>
      </View>

      {loading ? (
        <View style={{ flex: 1, alignItems: "center", justifyContent: "center" }}>
          <ActivityIndicator color={colors.brand} size="large" />
        </View>
      ) : (
        <FlatList
          data={invoices}
          keyExtractor={(i) => i.id}
          contentContainerStyle={{ padding: spacing.lg, paddingBottom: tabBarHeight + spacing.lg, gap: spacing.md, flexGrow: 1 }}
          showsVerticalScrollIndicator={false}
          ListEmptyComponent={
            <View style={{ flex: 1, justifyContent: "center", minHeight: 400 }}>
              <EmptyState icon="document-text-outline" title="No invoices yet" subtitle="Time to bill your first client. Tap + to create an invoice." testID="invoices-empty" />
              <View style={{ paddingHorizontal: spacing.xl }}>
                <PrimaryButton title="Create invoice" icon="add" onPress={openCreate} testID="invoices-empty-create" />
              </View>
            </View>
          }
          renderItem={({ item }) => (
            <Card onPress={() => openDetail(item)} testID={`invoice-row-${item.id}`} style={{ paddingVertical: spacing.md }}>
              <View style={{ flexDirection: "row", justifyContent: "space-between", alignItems: "center" }}>
                <View style={{ flex: 1, gap: 2 }}>
                  <AppText variant="body" style={{ fontWeight: "700" }}>{item.client_name}</AppText>
                  <AppText variant="caption">{item.number} · {prettyDate(item.issue_date)}</AppText>
                </View>
                <View style={{ alignItems: "flex-end", gap: 6 }}>
                  <AppText variant="heading">{gbp(item.total)}</AppText>
                  <Pill label={item.status} tone={STATUS_TONE[item.status]} />
                </View>
              </View>
            </Card>
          )}
        />
      )}

      {/* Create sheet */}
      <AppSheet ref={createRef}>
        <AppText variant="title">{editingId ? "Edit invoice" : "New invoice"}</AppText>

        <AppText variant="label">Client</AppText>
        <View style={{ flexDirection: "row", flexWrap: "wrap", gap: spacing.sm }}>
          {clients.map((c) => {
            const active = c.id === clientId;
            return (
              <Pressable
                key={c.id}
                testID={`invoice-client-${c.id}`}
                onPress={() => setClientId(c.id)}
                style={{
                  paddingHorizontal: spacing.md,
                  paddingVertical: spacing.sm,
                  borderRadius: 999,
                  backgroundColor: active ? colors.brandPrimary : colors.surfaceTertiary,
                  borderWidth: 1,
                  borderColor: active ? colors.brandPrimary : colors.border,
                }}
              >
                <AppText variant="caption" color={active ? colors.onBrandPrimary : colors.onSurface} style={{ fontWeight: "600" }}>{c.name}</AppText>
              </Pressable>
            );
          })}
        </View>

        <View style={{ flexDirection: "row", gap: spacing.md }}>
          <View style={{ flex: 1 }}>
            <AppText variant="label">Issue date</AppText>
            <DateButton value={issueDate} onPress={() => setPicker("issue")} />
          </View>
          <View style={{ flex: 1 }}>
            <AppText variant="label">Due date</AppText>
            <DateButton value={dueDate} placeholder="Optional" onPress={() => setPicker("due")} />
          </View>
        </View>

        <Divider />
        <AppText variant="label">Line items</AppText>
        {items.map((it, idx) => (
          <View key={idx} style={{ gap: spacing.sm, backgroundColor: colors.surfaceSecondary, padding: spacing.md, borderRadius: 12, borderWidth: 1, borderColor: colors.border }}>
            <Pressable
              testID={`invoice-item-choose-${idx}`}
              onPress={() => { setServiceQuery(""); setServicePickerFor(idx); }}
              style={{ flexDirection: "row", alignItems: "center", gap: 6, alignSelf: "flex-start", backgroundColor: colors.brandTertiary, paddingHorizontal: spacing.md, paddingVertical: 6, borderRadius: 999 }}
            >
              <Ionicons name="list-outline" size={15} color={colors.onBrandTertiary} />
              <AppText variant="caption" color={colors.onBrandTertiary} style={{ fontWeight: "700" }}>Choose a service</AppText>
            </Pressable>
            <Field value={it.description} onChangeText={(t) => setItems((p) => p.map((x, i) => (i === idx ? { ...x, description: t } : x)))} placeholder="Description" testID={`invoice-item-desc-${idx}`} />
            <View style={{ flexDirection: "row", gap: spacing.sm }}>
              <View style={{ flex: 1 }}>
                <Field label="Qty" value={it.quantity} onChangeText={(t) => setItems((p) => p.map((x, i) => (i === idx ? { ...x, quantity: t } : x)))} keyboardType="decimal-pad" testID={`invoice-item-qty-${idx}`} />
              </View>
              <View style={{ flex: 1.4 }}>
                <Field label="Rate (£)" value={it.unit_price} onChangeText={(t) => setItems((p) => p.map((x, i) => (i === idx ? { ...x, unit_price: t } : x)))} keyboardType="decimal-pad" testID={`invoice-item-rate-${idx}`} />
              </View>
              {items.length > 1 && (
                <Pressable onPress={() => setItems((p) => p.filter((_, i) => i !== idx))} style={{ justifyContent: "flex-end", paddingBottom: 12 }} testID={`invoice-item-remove-${idx}`}>
                  <Ionicons name="trash-outline" size={22} color={colors.error} />
                </Pressable>
              )}
            </View>
          </View>
        ))}
        <Pressable onPress={() => setItems((p) => [...p, { description: "", quantity: "1", unit_price: "" }])} style={{ flexDirection: "row", alignItems: "center", gap: 6, paddingVertical: spacing.sm }} testID="invoice-add-item">
          <Ionicons name="add-circle-outline" size={20} color={colors.brand} />
          <AppText variant="body" color={colors.brand} style={{ fontWeight: "600" }}>Add line</AppText>
        </Pressable>

        <Field label="Notes (optional)" value={notes} onChangeText={setNotes} placeholder="Payment terms, references..." multiline testID="invoice-notes" />

        <AppText variant="label">Status</AppText>
        <View style={{ flexDirection: "row", gap: spacing.sm }}>
          {(["draft", "sent", "paid"] as const).map((s) => (
            <Pressable
              key={s}
              testID={`invoice-status-${s}`}
              onPress={() => setStatus(s)}
              style={{ flex: 1, alignItems: "center", paddingVertical: spacing.sm, borderRadius: 10, backgroundColor: status === s ? colors.brandTertiary : colors.surfaceTertiary, borderWidth: 1, borderColor: status === s ? colors.brand : colors.border }}
            >
              <AppText variant="caption" color={status === s ? colors.brand : colors.onSurfaceTertiary} style={{ fontWeight: "700", textTransform: "capitalize" }}>{s}</AppText>
            </Pressable>
          ))}
        </View>

        <View style={{ flexDirection: "row", justifyContent: "space-between", alignItems: "center", marginTop: spacing.sm }}>
          <AppText variant="heading">Total</AppText>
          <AppText variant="title" color={colors.brand}>{gbp(total)}</AppText>
        </View>

        <PrimaryButton title={editingId ? "Save changes" : "Save invoice"} onPress={save} loading={saving} testID="invoice-save-button" />

        {picker && (
          <DateTimePicker
            value={(picker === "issue" ? issueDate : dueDate) || new Date()}
            mode="date"
            display={Platform.OS === "ios" ? "inline" : "default"}
            onChange={(e, d) => {
              if (Platform.OS !== "ios") setPicker(null);
              if (e.type === "dismissed") return;
              if (d) picker === "issue" ? setIssueDate(d) : setDueDate(d);
            }}
          />
        )}
        {Platform.OS === "ios" && picker && (
          <PrimaryButton title="Done" variant="outline" onPress={() => setPicker(null)} testID="date-done-button" />
        )}
      </AppSheet>

      {/* Detail sheet */}
      <AppSheet ref={detailRef} snapPoints={["70%"]}>
        {selected && (
          <View style={{ gap: spacing.md }}>
            <View style={{ flexDirection: "row", justifyContent: "space-between", alignItems: "flex-start" }}>
              <View>
                <AppText variant="title">{selected.number}</AppText>
                <AppText variant="caption">{selected.client_name}</AppText>
              </View>
              <Pill label={selected.status} tone={STATUS_TONE[selected.status]} />
            </View>

            <Card>
              {selected.items?.map((it: any, i: number) => (
                <View key={i} style={{ flexDirection: "row", justifyContent: "space-between", paddingVertical: 6 }}>
                  <AppText variant="body" style={{ flex: 1 }}>{it.description} {it.quantity > 1 ? `×${it.quantity}` : ""}</AppText>
                  <AppText variant="body" style={{ fontWeight: "600" }}>{gbp((it.quantity || 0) * (it.unit_price || 0))}</AppText>
                </View>
              ))}
              <Divider />
              <View style={{ flexDirection: "row", justifyContent: "space-between" }}>
                <AppText variant="heading">Total</AppText>
                <AppText variant="heading" color={colors.brand}>{gbp(selected.total)}</AppText>
              </View>
              <AppText variant="caption" style={{ marginTop: 4 }}>
                Issued {prettyDate(selected.issue_date)}{selected.paid_date ? ` · Paid ${prettyDate(selected.paid_date)}` : ""} · No VAT (exempt)
              </AppText>
            </Card>

            <PrimaryButton title="Share PDF" icon="share-outline" onPress={doShare} testID="invoice-share-button" />
            <View style={{ flexDirection: "row", gap: spacing.md }}>
              <View style={{ flex: 1 }}>
                <PrimaryButton title="Edit" icon="create-outline" variant="outline" onPress={() => openEdit(selected)} testID="invoice-edit-button" />
              </View>
              {selected.status !== "paid" && (
                <View style={{ flex: 1 }}>
                  <PrimaryButton title="Mark paid" icon="checkmark-circle-outline" variant="secondary" onPress={markPaid} testID="invoice-mark-paid-button" />
                </View>
              )}
            </View>
            <Pressable onPress={removeInvoice} style={{ alignItems: "center", paddingVertical: spacing.md }} testID="invoice-delete-button">
              <AppText variant="body" color={colors.error} style={{ fontWeight: "600" }}>Delete invoice</AppText>
            </Pressable>
          </View>
        )}
      </AppSheet>

      {/* Service picker */}
      <Modal visible={servicePickerFor !== null} transparent animationType="slide" onRequestClose={() => setServicePickerFor(null)}>
        <Pressable style={{ flex: 1, backgroundColor: "rgba(0,0,0,0.5)" }} onPress={() => setServicePickerFor(null)} testID="service-picker-backdrop" />
        <View style={{ position: "absolute", left: 0, right: 0, bottom: 0, top: insets.top + 40, backgroundColor: colors.surface, borderTopLeftRadius: 20, borderTopRightRadius: 20, padding: spacing.lg, paddingBottom: insets.bottom + spacing.lg, gap: spacing.md }}>
          <View style={{ flexDirection: "row", justifyContent: "space-between", alignItems: "center" }}>
            <AppText variant="heading">Choose a service</AppText>
            <IconButton icon="close" onPress={() => setServicePickerFor(null)} testID="service-picker-close" />
          </View>
          <View style={{ flexDirection: "row", alignItems: "center", gap: spacing.sm, backgroundColor: colors.surfaceTertiary, borderRadius: 12, paddingHorizontal: spacing.md, borderWidth: 1, borderColor: colors.border }}>
            <Ionicons name="search" size={18} color={colors.onSurfaceTertiary} />
            <TextInput
              testID="service-search-input"
              value={serviceQuery}
              onChangeText={setServiceQuery}
              placeholder="Search services..."
              placeholderTextColor={colors.onSurfaceTertiary}
              style={{ flex: 1, paddingVertical: spacing.md, color: colors.onSurface, fontSize: 16 }}
              autoFocus
            />
          </View>
          <FlatList
            data={filteredServices}
            keyExtractor={(s, i) => `${s.name}-${i}`}
            keyboardShouldPersistTaps="handled"
            showsVerticalScrollIndicator={false}
            contentContainerStyle={{ paddingBottom: insets.bottom + 40 }}
            renderItem={({ item }) => (
              <Pressable
                testID={`service-option-${item.name}`}
                onPress={() => applyService(item)}
                style={({ pressed }) => [{ flexDirection: "row", alignItems: "center", justifyContent: "space-between", paddingVertical: spacing.md, borderBottomWidth: 1, borderBottomColor: colors.divider }, pressed && { opacity: 0.6 }]}
              >
                <View style={{ flex: 1, flexDirection: "row", alignItems: "center", gap: spacing.sm }}>
                  {item.saved && <Ionicons name="star" size={14} color={colors.brandSecondary} />}
                  <AppText variant="body">{item.name}</AppText>
                </View>
                {item.price != null && item.price !== "" ? <AppText variant="body" color={colors.brand} style={{ fontWeight: "700" }}>{gbp(Number(item.price))}</AppText> : null}
              </Pressable>
            )}
          />
        </View>
      </Modal>
    </View>
  );
}

function DateButton({ value, onPress, placeholder }: { value: Date | null; onPress: () => void; placeholder?: string }) {
  const { colors, radius, spacing } = useTheme();
  return (
    <Pressable
      onPress={onPress}
      style={{ backgroundColor: colors.surfaceTertiary, borderRadius: radius.md, paddingHorizontal: spacing.md, paddingVertical: spacing.md + 2, borderWidth: 1, borderColor: colors.border, minHeight: 52, justifyContent: "center" }}
    >
      <AppText variant="body" color={value ? colors.onSurface : colors.onSurfaceTertiary}>
        {value ? prettyDate(toISODate(value)) : placeholder || "Select"}
      </AppText>
    </Pressable>
  );
}
