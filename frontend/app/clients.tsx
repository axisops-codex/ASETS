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
  const [saving, setSaving] = useState(false);

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
    setName(""); setContact(""); setEmail(""); setAddress(""); setRate("");
    sheetRef.current?.expand();
  };

  const openEdit = (c: any) => {
    setEditing(c);
    setName(c.name); setContact(c.contact_name || ""); setEmail(c.email || ""); setAddress(c.address || ""); setRate(c.rate ? String(c.rate) : "");
    sheetRef.current?.expand();
  };

  const save = async () => {
    if (!name.trim()) return toast.show("Enter a company name", "error");
    setSaving(true);
    const body = { name: name.trim(), contact_name: contact.trim(), email: email.trim(), address: address.trim(), notes: "", rate: rate ? parseFloat(rate) : null };
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
