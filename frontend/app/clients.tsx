import React, { useCallback, useRef, useState } from "react";
import { View, FlatList, Pressable, ActivityIndicator } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { useFocusEffect, useRouter } from "expo-router";
import { Ionicons } from "@expo/vector-icons";
import BottomSheet from "@gorhom/bottom-sheet";
import { useTheme } from "@/src/theme/ThemeProvider";
import { api } from "@/src/api/client";
import { useToast } from "@/src/components/Toast";
import { AppSheet } from "@/src/components/AppSheet";
import { AppText, Card, Field, PrimaryButton, EmptyState, IconButton } from "@/src/components/ui";

export default function Clients() {
  const { colors, spacing } = useTheme();
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const toast = useToast();

  const [clients, setClients] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const sheetRef = useRef<BottomSheet>(null);

  const [editing, setEditing] = useState<any>(null);
  const [name, setName] = useState("");
  const [contact, setContact] = useState("");
  const [email, setEmail] = useState("");
  const [address, setAddress] = useState("");
  const [rate, setRate] = useState("");
  const [companyNumber, setCompanyNumber] = useState("");
  const [saving, setSaving] = useState(false);
  const [chLoading, setChLoading] = useState(false);
  const [chResults, setChResults] = useState<any[]>([]);

  const load = useCallback(async () => {
    try {
      setClients(await api.clients());
    } catch (e: any) {
      toast.show(e.message || "Could not load", "error");
    } finally {
      setLoading(false);
    }
  }, []);

  useFocusEffect(useCallback(() => { load(); }, [load]));

  const openNew = () => {
    setEditing(null);
    setName(""); setContact(""); setEmail(""); setAddress(""); setRate(""); setCompanyNumber("");
    setChResults([]);
    sheetRef.current?.expand();
  };

  const openEdit = (c: any) => {
    setEditing(c);
    setName(c.name); setContact(c.contact_name || ""); setEmail(c.email || ""); setAddress(c.address || ""); setRate(c.rate ? String(c.rate) : ""); setCompanyNumber(c.company_number || "");
    setChResults([]);
    sheetRef.current?.expand();
  };

  const searchCompany = async () => {
    if (name.trim().length < 2) return toast.show("Type the company name first", "info");
    setChLoading(true);
    try {
      const res = await api.companiesSearch(name.trim());
      setChResults(res.items || []);
      if (!res.items?.length) toast.show("No companies found", "info");
    } catch (e: any) {
      toast.show(e.message || "Lookup unavailable", "error");
    } finally {
      setChLoading(false);
    }
  };

  const pickCompany = (c: any) => {
    setName(c.company_name || name);
    setAddress(c.address || address);
    setCompanyNumber(c.company_number || "");
    setChResults([]);
    toast.show("Company details filled in", "success");
  };

  const save = async () => {
    if (!name.trim()) return toast.show("Enter a company name", "error");
    setSaving(true);
    const body = { name: name.trim(), contact_name: contact.trim(), email: email.trim(), address: address.trim(), company_number: companyNumber.trim(), notes: "", rate: rate ? parseFloat(rate) : null };
    try {
      if (editing) await api.updateClient(editing.id, body);
      else await api.createClient(body);
      sheetRef.current?.close();
      toast.show(editing ? "Client updated" : "Client added", "success");
      load();
    } catch (e: any) {
      toast.show(e.message || "Could not save", "error");
    } finally {
      setSaving(false);
    }
  };

  const remove = async () => {
    if (!editing) return;
    try {
      await api.deleteClient(editing.id);
      sheetRef.current?.close();
      toast.show("Client deleted", "success");
      load();
    } catch (e: any) {
      toast.show(e.message, "error");
    }
  };

  return (
    <View style={{ flex: 1, backgroundColor: colors.surface }}>
      <View style={{ paddingTop: insets.top + spacing.sm, paddingHorizontal: spacing.lg, paddingBottom: spacing.md, backgroundColor: colors.surface, borderBottomWidth: 1, borderBottomColor: colors.border, flexDirection: "row", alignItems: "center", justifyContent: "space-between" }}>
        <View style={{ flexDirection: "row", alignItems: "center", gap: spacing.sm }}>
          <IconButton icon="chevron-back" onPress={() => router.back()} testID="clients-back-button" />
          <AppText variant="title">Clients</AppText>
        </View>
        <IconButton icon="add" onPress={openNew} color={colors.brand} testID="client-new-button" />
      </View>

      {loading ? (
        <View style={{ flex: 1, alignItems: "center", justifyContent: "center" }}>
          <ActivityIndicator color={colors.brand} size="large" />
        </View>
      ) : (
        <FlatList
          data={clients}
          keyExtractor={(c) => c.id}
          contentContainerStyle={{ padding: spacing.lg, gap: spacing.md, flexGrow: 1, paddingBottom: 40 }}
          showsVerticalScrollIndicator={false}
          ListEmptyComponent={
            <View style={{ flex: 1, justifyContent: "center", minHeight: 400 }}>
              <EmptyState icon="people-outline" title="No clients yet" subtitle="Add the companies that contract your services." testID="clients-empty" />
              <View style={{ paddingHorizontal: spacing.xl }}>
                <PrimaryButton title="Add client" icon="add" onPress={openNew} testID="clients-empty-create" />
              </View>
            </View>
          }
          renderItem={({ item }) => (
            <Card onPress={() => openEdit(item)} testID={`client-row-${item.id}`}>
              <View style={{ flexDirection: "row", alignItems: "center", gap: spacing.md }}>
                <View style={{ width: 44, height: 44, borderRadius: 14, backgroundColor: colors.brandTertiary, alignItems: "center", justifyContent: "center" }}>
                  <AppText variant="heading" color={colors.brand}>{(item.name || "?").charAt(0).toUpperCase()}</AppText>
                </View>
                <View style={{ flex: 1 }}>
                  <AppText variant="body" style={{ fontWeight: "700" }}>{item.name}</AppText>
                  <AppText variant="caption">{item.contact_name || item.email || "Tap to edit"}</AppText>
                </View>
                <Ionicons name="chevron-forward" size={18} color={colors.onSurfaceTertiary} />
              </View>
            </Card>
          )}
        />
      )}

      <AppSheet ref={sheetRef} snapPoints={["80%"]}>
        <AppText variant="title">{editing ? "Edit client" : "New client"}</AppText>
        <Field label="Company name" value={name} onChangeText={setName} placeholder="e.g. Wellbeing Clinics Ltd" autoCapitalize="words" testID="client-name-input" />
        <Pressable
          testID="client-find-company"
          onPress={searchCompany}
          style={{ flexDirection: "row", alignItems: "center", gap: 6, alignSelf: "flex-start", backgroundColor: colors.brandTertiary, paddingHorizontal: spacing.md, paddingVertical: 8, borderRadius: 999 }}
        >
          {chLoading ? <ActivityIndicator size="small" color={colors.brand} /> : <Ionicons name="search" size={15} color={colors.onBrandTertiary} />}
          <AppText variant="caption" color={colors.onBrandTertiary} style={{ fontWeight: "700" }}>Find on Companies House</AppText>
        </Pressable>
        {chResults.length > 0 && (
          <View style={{ backgroundColor: colors.surfaceSecondary, borderRadius: 12, borderWidth: 1, borderColor: colors.border, overflow: "hidden" }}>
            {chResults.map((c, i) => (
              <Pressable
                key={c.company_number}
                testID={`ch-result-${c.company_number}`}
                onPress={() => pickCompany(c)}
                style={({ pressed }) => [{ padding: spacing.md, borderBottomWidth: i < chResults.length - 1 ? 1 : 0, borderBottomColor: colors.divider }, pressed && { opacity: 0.6 }]}
              >
                <AppText variant="body" style={{ fontWeight: "600" }}>{c.company_name}</AppText>
                <AppText variant="caption">{c.company_number}{c.address ? ` · ${c.address}` : ""}</AppText>
              </Pressable>
            ))}
          </View>
        )}
        {companyNumber ? <AppText variant="caption" color={colors.brand}>Company no. {companyNumber}</AppText> : null}
        <Field label="Contact person" value={contact} onChangeText={setContact} placeholder="Optional" autoCapitalize="words" testID="client-contact-input" />
        <Field label="Email" value={email} onChangeText={setEmail} placeholder="billing@company.com" keyboardType="email-address" autoCapitalize="none" testID="client-email-input" />
        <Field label="Billing address" value={address} onChangeText={setAddress} placeholder="Optional" multiline testID="client-address-input" />
        <Field label="Default rate £/hr (optional)" value={rate} onChangeText={setRate} placeholder="e.g. 60" keyboardType="decimal-pad" testID="client-rate-input" />
        <PrimaryButton title={editing ? "Save changes" : "Add client"} onPress={save} loading={saving} testID="client-save-button" />
        {editing && (
          <Pressable onPress={remove} style={{ alignItems: "center", paddingVertical: spacing.md }} testID="client-delete-button">
            <AppText variant="body" color={colors.error} style={{ fontWeight: "600" }}>Delete client</AppText>
          </Pressable>
        )}
      </AppSheet>
    </View>
  );
}
