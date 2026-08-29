import React, { useState } from "react";
import { View, ScrollView, Pressable, Switch, Linking } from "react-native";
import * as WebBrowser from "expo-web-browser";
import { KeyboardAwareScrollView } from "react-native-keyboard-controller";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { useRouter } from "expo-router";
import { Ionicons } from "@expo/vector-icons";
import * as Haptics from "expo-haptics";
import { useTheme } from "@/src/theme/ThemeProvider";
import { useScreenBottomPadding } from "@/src/hooks/use-tab-bar-height";
import { useAuth } from "@/src/context/AuthContext";
import { useBiometric } from "@/src/context/BiometricContext";
import { api } from "@/src/api/client";
import { useToast } from "@/src/components/Toast";
import { AppText, Card, Field, PrimaryButton, IconButton, Divider } from "@/src/components/ui";
import { LogoLockup } from "@/src/components/Logo";
import { gbp } from "@/src/utils/format";
import { LEGAL, SUPPORT_EMAIL, VERSION_LABEL } from "@/src/config/app";

const CARD_OPTIONS = [
  { key: "take_home", label: "Estimated take home", icon: "wallet-outline" },
  { key: "hmrc", label: "HMRC estimate", icon: "calculator-outline" },
  { key: "cashflow", label: "Cash flow chart", icon: "bar-chart-outline" },
  { key: "recent", label: "Paid vs outstanding", icon: "swap-horizontal-outline" },
];

export default function Settings() {
  const { colors, spacing, mode, setMode, scheme } = useTheme();
  const insets = useSafeAreaInsets();
  const bottomPadding = useScreenBottomPadding(40);
  const router = useRouter();
  const { user, logout, refreshUser } = useAuth();
  const { supported: bioSupported, enabled: bioEnabled, enable: bioEnable, disable: bioDisable } = useBiometric();
  const toast = useToast();

  const [name, setName] = useState(user?.name || "");
  const [business, setBusiness] = useState(user?.business_name || "");
  const [address, setAddress] = useState(user?.address || "");
  const [city, setCity] = useState((user as any)?.city || "");
  const [postcode, setPostcode] = useState((user as any)?.postcode || "");
  const [utr, setUtr] = useState(user?.utr || "");
  const [companyReg, setCompanyReg] = useState((user as any)?.company_reg || "");
  const [vatNumber, setVatNumber] = useState((user as any)?.vat_number || "");
  const [savingProfile, setSavingProfile] = useState(false);

  const bank0 = (user as any)?.bank || {};
  const [bankName, setBankName] = useState(bank0.bank_name || "");
  const [accName, setAccName] = useState(bank0.account_name || "");
  const [sortCode, setSortCode] = useState(bank0.sort_code || "");
  const [accNumber, setAccNumber] = useState(bank0.account_number || "");
  const [reference, setReference] = useState(bank0.reference || "Please use the invoice number");
  const [savingBank, setSavingBank] = useState(false);

  const [services, setServices] = useState<any[]>((user as any)?.services || []);
  const [svcName, setSvcName] = useState("");
  const [svcPrice, setSvcPrice] = useState("");
  const [svcUnit, setSvcUnit] = useState<"session" | "hour" | "fixed">("session");

  const [confirmDelete, setConfirmDelete] = useState(false);
  const [deleting, setDeleting] = useState(false);

  const openLink = (url: string) => {
    WebBrowser.openBrowserAsync(url).catch(() => Linking.openURL(url).catch(() => {}));
  };

  const deleteAccount = async () => {
    setDeleting(true);
    try {
      await api.deleteAccount();
      await logout();
      router.replace("/(auth)/login");
      toast.show("Your account and all its data were deleted.");
    } catch (e: any) {
      toast.show(e?.message || "Could not delete the account. Please try again.");
    } finally {
      setDeleting(false);
      setConfirmDelete(false);
    }
  };

  const activeCards: string[] = user?.settings?.cards || CARD_OPTIONS.map((c) => c.key);

  const saveProfile = async () => {
    setSavingProfile(true);
    try {
      const updated = await api.updateProfile({ name, business_name: business, address, city, postcode, utr, company_reg: companyReg, vat_number: vatNumber });
      refreshUser(updated);
      toast.show("Details saved", "success");
    } catch (e: any) {
      toast.show(e.message || "Could not save", "error");
    } finally {
      setSavingProfile(false);
    }
  };

  const saveBank = async () => {
    setSavingBank(true);
    try {
      const updated = await api.updateProfile({ bank: { bank_name: bankName, account_name: accName, sort_code: sortCode, account_number: accNumber, reference } });
      refreshUser(updated);
      toast.show("Payment details saved", "success");
    } catch (e: any) {
      toast.show(e.message || "Could not save", "error");
    } finally {
      setSavingBank(false);
    }
  };

  const persistServices = async (next: any[]) => {
    setServices(next);
    try {
      const updated = await api.updateProfile({ services: next });
      refreshUser(updated);
    } catch (e: any) {
      toast.show(e.message, "error");
    }
  };

  const addService = () => {
    if (!svcName.trim()) return toast.show("Enter a service name", "error");
    const next = [...services, { id: Date.now().toString(), name: svcName.trim(), price: svcPrice ? parseFloat(svcPrice) : undefined, unit: svcUnit }];
    persistServices(next);
    setSvcName(""); setSvcPrice(""); setSvcUnit("session");
    toast.show("Service added", "success");
  };

  const removeService = (id: string) => persistServices(services.filter((s) => s.id !== id));

  const toggleCard = async (key: string) => {
    Haptics.selectionAsync().catch(() => {});
    const next = activeCards.includes(key) ? activeCards.filter((k) => k !== key) : [...activeCards, key];
    const settings = { ...(user?.settings || {}), cards: next };
    try {
      const updated = await api.updateProfile({ settings });
      refreshUser(updated);
    } catch (e: any) {
      toast.show(e.message, "error");
    }
  };

  const setTheme = async (m: "light" | "dark" | "system") => {
    Haptics.selectionAsync().catch(() => {});
    setMode(m);
    const settings = { ...(user?.settings || {}), theme: m };
    api.updateProfile({ settings }).then(refreshUser).catch(() => {});
  };

  const toggleBiometric = async () => {
    Haptics.selectionAsync().catch(() => {});
    if (bioEnabled) {
      await bioDisable();
      toast.show("App lock turned off", "success");
    } else {
      const ok = await bioEnable();
      if (ok) toast.show("App lock turned on", "success");
      else toast.show("Could not verify — try again", "error");
    }
  };

  return (
    <View style={{ flex: 1, backgroundColor: colors.surface }}>
      <View style={{ paddingTop: insets.top + spacing.sm, paddingHorizontal: spacing.lg, paddingBottom: spacing.md, backgroundColor: colors.surface, borderBottomWidth: 1, borderBottomColor: colors.border, flexDirection: "row", alignItems: "center", gap: spacing.sm }}>
        <IconButton icon="chevron-back" onPress={() => router.back()} testID="settings-back-button" />
        <AppText variant="title">Settings</AppText>
      </View>

      <KeyboardAwareScrollView bottomOffset={24} contentContainerStyle={{ padding: spacing.lg, paddingBottom: bottomPadding, gap: spacing.lg }} keyboardShouldPersistTaps="handled">
        <View style={{ paddingTop: spacing.xs, paddingBottom: spacing.sm }}>
          <LogoLockup size={52} />
        </View>

        {/* Appearance */}
        <View style={{ gap: spacing.sm }}>
          <AppText variant="label">Appearance</AppText>
          <Card style={{ flexDirection: "row", gap: spacing.sm }}>
            {(["light", "dark", "system"] as const).map((m) => {
              const active = mode === m;
              const icon = m === "light" ? "sunny-outline" : m === "dark" ? "moon-outline" : "phone-portrait-outline";
              return (
                <Pressable
                  key={m}
                  testID={`theme-${m}`}
                  onPress={() => setTheme(m)}
                  style={{ flex: 1, alignItems: "center", gap: 6, paddingVertical: spacing.md, borderRadius: 12, backgroundColor: active ? colors.brandTertiary : colors.surfaceTertiary, borderWidth: 1, borderColor: active ? colors.brand : colors.border }}
                >
                  <Ionicons name={icon as any} size={22} color={active ? colors.brand : colors.onSurfaceTertiary} />
                  <AppText variant="caption" color={active ? colors.brand : colors.onSurfaceTertiary} style={{ fontWeight: "700", textTransform: "capitalize" }}>{m}</AppText>
                </Pressable>
              );
            })}
          </Card>
        </View>

        {/* Dashboard cards */}
        <View style={{ gap: spacing.sm }}>
          <AppText variant="label">Dashboard cards</AppText>
          <Card style={{ gap: 0 }}>
            {CARD_OPTIONS.map((c, i) => (
              <View key={c.key}>
                <View style={{ flexDirection: "row", alignItems: "center", gap: spacing.md, paddingVertical: spacing.sm }}>
                  <View style={{ width: 36, height: 36, borderRadius: 10, backgroundColor: colors.brandTertiary, alignItems: "center", justifyContent: "center" }}>
                    <Ionicons name={c.icon as any} size={18} color={colors.brand} />
                  </View>
                  <AppText variant="body" style={{ flex: 1, fontWeight: "600" }}>{c.label}</AppText>
                  <Switch
                    testID={`card-toggle-${c.key}`}
                    value={activeCards.includes(c.key)}
                    onValueChange={() => toggleCard(c.key)}
                    trackColor={{ true: colors.brand, false: colors.borderStrong }}
                    thumbColor="#fff"
                  />
                </View>
                {i < CARD_OPTIONS.length - 1 && <View style={{ height: 1, backgroundColor: colors.divider }} />}
              </View>
            ))}
          </Card>
        </View>

        {/* Security */}
        <View style={{ gap: spacing.sm }}>
          <AppText variant="label">Security</AppText>
          <Card>
            <View style={{ flexDirection: "row", alignItems: "center", gap: spacing.md }}>
              <View style={{ width: 36, height: 36, borderRadius: 10, backgroundColor: colors.brandTertiary, alignItems: "center", justifyContent: "center" }}>
                <Ionicons name="finger-print" size={18} color={colors.brand} />
              </View>
              <View style={{ flex: 1 }}>
                <AppText variant="body" style={{ fontWeight: "600" }}>Unlock with Face ID / fingerprint</AppText>
                <AppText variant="caption">{bioSupported ? "Require biometrics to open the app" : "Set up Face ID or a fingerprint on your device first"}</AppText>
              </View>
              <Switch
                testID="biometric-toggle"
                value={bioEnabled}
                disabled={!bioSupported}
                onValueChange={toggleBiometric}
                trackColor={{ true: colors.brand, false: colors.borderStrong }}
                thumbColor="#fff"
              />
            </View>
          </Card>
        </View>

        {/* Business profile */}
        <View style={{ gap: spacing.sm }}>
          <AppText variant="label">Your details (shown on invoices)</AppText>
          <Card style={{ gap: spacing.md }}>
            <Field label="Your name" value={name} onChangeText={setName} placeholder="Dr. Sarah Jones" autoCapitalize="words" testID="settings-name-input" />
            <Field label="Practice / business name" value={business} onChangeText={setBusiness} placeholder="Sarah Jones Psychology" autoCapitalize="words" testID="settings-business-input" />
            <Field label="Address" value={address} onChangeText={setAddress} placeholder="Address line" multiline testID="settings-address-input" />
            <View style={{ flexDirection: "row", gap: spacing.md }}>
              <View style={{ flex: 1.4 }}><Field label="City" value={city} onChangeText={setCity} placeholder="London" autoCapitalize="words" testID="settings-city-input" /></View>
              <View style={{ flex: 1 }}><Field label="Postcode" value={postcode} onChangeText={setPostcode} placeholder="SW1A 1AA" autoCapitalize="characters" testID="settings-postcode-input" /></View>
            </View>
            <View style={{ flexDirection: "row", gap: spacing.md }}>
              <View style={{ flex: 1 }}><Field label="Company Reg (opt)" value={companyReg} onChangeText={setCompanyReg} placeholder="12345678" testID="settings-companyreg-input" /></View>
              <View style={{ flex: 1 }}><Field label="VAT No (opt)" value={vatNumber} onChangeText={setVatNumber} placeholder="GB123456789" autoCapitalize="characters" testID="settings-vat-input" /></View>
            </View>
            <Field label="UTR (optional)" value={utr} onChangeText={setUtr} placeholder="10-digit tax reference" keyboardType="numeric" testID="settings-utr-input" />
            <PrimaryButton title="Save details" onPress={saveProfile} loading={savingProfile} testID="settings-save-profile" />
          </Card>
        </View>

        {/* Payment details */}
        <View style={{ gap: spacing.sm }}>
          <AppText variant="label">Payment details (shown on invoices)</AppText>
          <Card style={{ gap: spacing.md }}>
            <Field label="Bank" value={bankName} onChangeText={setBankName} placeholder="e.g. Barclays" autoCapitalize="words" testID="settings-bank-input" />
            <Field label="Account name" value={accName} onChangeText={setAccName} placeholder="Account holder" autoCapitalize="words" testID="settings-accname-input" />
            <View style={{ flexDirection: "row", gap: spacing.md }}>
              <View style={{ flex: 1 }}><Field label="Sort code" value={sortCode} onChangeText={setSortCode} placeholder="20-00-00" testID="settings-sortcode-input" /></View>
              <View style={{ flex: 1.2 }}><Field label="Account no." value={accNumber} onChangeText={setAccNumber} placeholder="12345678" keyboardType="numeric" testID="settings-accnumber-input" /></View>
            </View>
            <Field label="Reference" value={reference} onChangeText={setReference} placeholder="Please use the invoice number" testID="settings-reference-input" />
            <PrimaryButton title="Save payment details" onPress={saveBank} loading={savingBank} variant="secondary" testID="settings-save-bank" />
          </Card>
        </View>

        {/* Your services */}
        <View style={{ gap: spacing.sm }}>
          <AppText variant="label">Your services (dropdown on invoices)</AppText>
          <Card style={{ gap: spacing.md }}>
            {services.length === 0 ? (
              <AppText variant="caption">Add the services you offer, with a default price. They'll appear in the invoice line dropdown.</AppText>
            ) : (
              services.map((s) => (
                <View key={s.id} style={{ flexDirection: "row", alignItems: "center", gap: spacing.sm }} testID={`service-item-${s.id}`}>
                  <View style={{ flex: 1 }}>
                    <AppText variant="body" style={{ fontWeight: "600" }}>{s.name}</AppText>
                    <AppText variant="caption">{s.price != null ? gbp(Number(s.price)) : "No default price"} · per {s.unit}</AppText>
                  </View>
                  <Pressable onPress={() => removeService(s.id)} hitSlop={8} testID={`service-remove-${s.id}`}>
                    <Ionicons name="trash-outline" size={20} color={colors.error} />
                  </Pressable>
                </View>
              ))
            )}
            <View style={{ height: 1, backgroundColor: colors.divider }} />
            <Field label="Service name" value={svcName} onChangeText={setSvcName} placeholder="e.g. CBT session" testID="service-name-input" />
            <View style={{ flexDirection: "row", gap: spacing.md, alignItems: "flex-end" }}>
              <View style={{ flex: 1 }}><Field label="Price £ (opt)" value={svcPrice} onChangeText={setSvcPrice} placeholder="90" keyboardType="decimal-pad" testID="service-price-input" /></View>
              <View style={{ flex: 1.4, gap: 4 }}>
                <AppText variant="label">Unit</AppText>
                <View style={{ flexDirection: "row", gap: 6 }}>
                  {(["session", "hour", "fixed"] as const).map((u) => (
                    <Pressable key={u} testID={`service-unit-${u}`} onPress={() => setSvcUnit(u)} style={{ flex: 1, alignItems: "center", paddingVertical: 10, borderRadius: 10, backgroundColor: svcUnit === u ? colors.brandTertiary : colors.surfaceTertiary, borderWidth: 1, borderColor: svcUnit === u ? colors.brand : colors.border }}>
                      <AppText variant="caption" color={svcUnit === u ? colors.brand : colors.onSurfaceTertiary} style={{ fontWeight: "700" }}>{u}</AppText>
                    </Pressable>
                  ))}
                </View>
              </View>
            </View>
            <PrimaryButton title="Add service" icon="add" onPress={addService} variant="outline" testID="service-add-button" />
          </Card>
        </View>

        {/* HMRC */}
        <View style={{ gap: spacing.sm }}>
          <AppText variant="label">HMRC</AppText>
          <Card style={{ gap: spacing.md }}>
            <AppText variant="caption">
              Connect ASETS to HMRC to send your quarterly updates for Making Tax Digital, straight from the app.
            </AppText>
            <PrimaryButton title="HMRC filing" icon="cloud-upload-outline" variant="outline"
                           onPress={() => router.push("/hmrc")} testID="settings-hmrc-button" />
          </Card>
        </View>

        {/* Legal & support */}
        <View style={{ gap: spacing.sm }}>
          <AppText variant="label">Legal &amp; support</AppText>
          <Card style={{ gap: spacing.md }}>
            {[
              { label: "Privacy Policy", icon: "shield-checkmark-outline", url: LEGAL.privacy, id: "privacy" },
              { label: "Terms of Use", icon: "document-text-outline", url: LEGAL.terms, id: "terms" },
              { label: "Help & FAQ", icon: "help-circle-outline", url: LEGAL.support, id: "support" },
            ].map((row) => (
              <Pressable
                key={row.id}
                testID={`settings-link-${row.id}`}
                onPress={() => openLink(row.url)}
                style={{ flexDirection: "row", alignItems: "center", gap: spacing.md }}
              >
                <Ionicons name={row.icon as any} size={20} color={colors.onSurfaceTertiary} />
                <AppText variant="body" style={{ flex: 1 }}>{row.label}</AppText>
                <Ionicons name="open-outline" size={16} color={colors.onSurfaceTertiary} />
              </Pressable>
            ))}
            <View style={{ height: 1, backgroundColor: colors.divider }} />
            <Pressable
              testID="settings-contact-support"
              onPress={() => Linking.openURL(`mailto:${SUPPORT_EMAIL}?subject=ASETS%20support`).catch(() => {})}
              style={{ flexDirection: "row", alignItems: "center", gap: spacing.md }}
            >
              <Ionicons name="mail-outline" size={20} color={colors.onSurfaceTertiary} />
              <AppText variant="body" style={{ flex: 1 }}>Contact support</AppText>
              <AppText variant="caption">{SUPPORT_EMAIL}</AppText>
            </Pressable>
          </Card>
        </View>

        <Divider />
        <View style={{ gap: spacing.xs }}>
          <AppText variant="caption">{user?.email}</AppText>
          <PrimaryButton title="Sign out" icon="log-out-outline" variant="outline" onPress={async () => { await logout(); router.replace("/(auth)/login"); }} testID="settings-logout-button" />
        </View>

        {/* Danger zone — in-app account deletion is required by both app stores */}
        <View style={{ gap: spacing.sm }}>
          <AppText variant="label">Delete account</AppText>
          <Card style={{ gap: spacing.md, borderColor: colors.error }}>
            <AppText variant="caption">
              Permanently deletes your profile, clients, invoices, expenses and receipt photos. This cannot be undone —
              export your CSV from the Tax tab first if you want a copy.
            </AppText>
            {confirmDelete ? (
              <View style={{ gap: spacing.sm }}>
                <AppText variant="body" style={{ fontWeight: "700" }} color={colors.error}>
                  Delete everything for {user?.email}?
                </AppText>
                <PrimaryButton
                  title="Yes, delete my account"
                  icon="trash-outline"
                  variant="secondary"
                  loading={deleting}
                  onPress={deleteAccount}
                  testID="settings-delete-confirm"
                />
                <PrimaryButton
                  title="Cancel"
                  variant="outline"
                  onPress={() => setConfirmDelete(false)}
                  testID="settings-delete-cancel"
                />
              </View>
            ) : (
              <PrimaryButton
                title="Delete account"
                icon="trash-outline"
                variant="outline"
                onPress={() => setConfirmDelete(true)}
                testID="settings-delete-button"
              />
            )}
          </Card>
        </View>

        <AppText variant="caption" style={{ textAlign: "center" }}>ASETS v{VERSION_LABEL}</AppText>
      </KeyboardAwareScrollView>
    </View>
  );
}
