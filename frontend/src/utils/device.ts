import { Dimensions, PixelRatio, Platform } from "react-native";
import * as Device from "expo-device";
import * as Network from "expo-network";
import { storage } from "@/src/utils/storage";
import { APP_VERSION } from "@/src/config/app";

/**
 * Device facts HMRC requires on every Making Tax Digital call.
 *
 * HMRC classifies this app as MOBILE_APP_VIA_SERVER: the phone collects
 * what only the phone can know, the API adds the rest and forwards the
 * call. Missing or invented values are the most common reason a
 * submission is rejected, so everything here is measured, and anything
 * we cannot measure is left out rather than guessed.
 *
 * Sent as one base64url JSON blob in the `X-ASETS-Device` header.
 */
const DEVICE_ID_KEY = "asets_device_id";
// Written by BiometricContext; read here so a submission can honestly
// declare that a second factor was used.
const BIOMETRIC_PREF_KEY = "psybooks_biometric";

/** A UUID generated once per install and kept in the secure store. */
async function deviceId(): Promise<string> {
  const existing = await storage.secureGet<string>(DEVICE_ID_KEY, "");
  if (existing && existing.length === 36) return existing;
  const fresh = "xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx".replace(/[xy]/g, (c) => {
    const r = (Math.random() * 16) | 0;
    return (c === "x" ? r : (r & 0x3) | 0x8).toString(16);
  });
  await storage.secureSet(DEVICE_ID_KEY, fresh);
  return fresh;
}

/** "UTC+01:00" — HMRC's format, not an IANA name. */
function timezone(): string {
  const offsetMinutes = -new Date().getTimezoneOffset();
  const sign = offsetMinutes >= 0 ? "+" : "-";
  const abs = Math.abs(offsetMinutes);
  const pad = (n: number) => String(n).padStart(2, "0");
  return `UTC${sign}${pad(Math.floor(abs / 60))}:${pad(abs % 60)}`;
}

function isoMillis(): string {
  return new Date().toISOString().replace(/(\.\d{3})\d*Z$/, "$1Z");
}

/**
 * HMRC's Gov-Client-Multi-Factor. Reported only when the app lock is
 * actually switched on — declaring a factor that was not used would be
 * worse than omitting the header.
 *
 * The reference is derived from the device id so HMRC can correlate
 * submissions from the same install without it identifying anything.
 */
async function multiFactor(deviceIdentifier: string) {
  try {
    const pref = await storage.secureGet<string>(BIOMETRIC_PREF_KEY, "");
    if (pref !== "on") return [];
    return [{
      type: "OTHER",
      timestamp: isoMillis(),
      reference: simpleHash(`asets-biometric:${deviceIdentifier}`),
    }];
  } catch {
    return [];
  }
}

/** Small, stable, non-reversible. Not a security boundary — an identifier. */
function simpleHash(input: string): string {
  let h1 = 0x811c9dc5;
  let h2 = 0x01000193;
  for (let i = 0; i < input.length; i++) {
    h1 = Math.imul(h1 ^ input.charCodeAt(i), 16777619) >>> 0;
    h2 = Math.imul(h2 + input.charCodeAt(i), 2246822519) >>> 0;
  }
  return (h1.toString(16) + h2.toString(16)).padStart(16, "0");
}

async function localIps(): Promise<string[]> {
  try {
    const ip = await Network.getIpAddressAsync();
    return ip ? [ip] : [];
  } catch {
    return [];
  }
}

export async function collectDeviceInfo() {
  const screen = Dimensions.get("screen");
  const window = Dimensions.get("window");
  const scale = PixelRatio.get();
  const identifier = await deviceId();

  return {
    deviceId: identifier,
    timezone: timezone(),
    localIps: await localIps(),
    localIpsTimestamp: isoMillis(),
    screens: {
      // HMRC wants physical pixels; React Native reports density pixels.
      width: Math.round(screen.width * scale),
      height: Math.round(screen.height * scale),
      scalingFactor: scale,
      colourDepth: 32,
    },
    windowSize: {
      width: Math.round(window.width * scale),
      height: Math.round(window.height * scale),
    },
    os: {
      family: Platform.OS === "ios" ? "iOS" : Platform.OS === "android" ? "Android" : "web",
      version: String(Device.osVersion ?? Platform.Version ?? ""),
      manufacturer: Device.manufacturer ?? (Platform.OS === "ios" ? "Apple" : ""),
      model: Device.modelId || Device.modelName || "",
    },
    appVersion: APP_VERSION,
    multiFactor: await multiFactor(identifier),
  };
}

function base64url(input: string): string {
  // btoa exists on Hermes and on web; the manual path covers neither
  // being available.
  const bytes = new TextEncoder().encode(input);
  let binary = "";
  bytes.forEach((b) => (binary += String.fromCharCode(b)));
  const base64 = typeof btoa === "function" ? btoa(binary) : globalThis.Buffer.from(input).toString("base64");
  return base64.replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}

/** The `X-ASETS-Device` header value, or {} if it cannot be built. */
export async function deviceHeader(): Promise<Record<string, string>> {
  try {
    return { "X-ASETS-Device": base64url(JSON.stringify(await collectDeviceInfo())) };
  } catch {
    return {};
  }
}
