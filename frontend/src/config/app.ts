import Constants from "expo-constants";

/** Backend origin, injected at build time (see eas.json → build.<profile>.env). */
export const BACKEND_URL = (process.env.EXPO_PUBLIC_BACKEND_URL || "").replace(/\/+$/, "");

export const SUPPORT_EMAIL = "ops@axisbsolutions.com";

/**
 * Legal pages are served by the API itself, so the URL always matches the
 * environment the build points at (and store listings never 404).
 */
export const LEGAL = {
  privacy: `${BACKEND_URL}/legal/privacy`,
  terms: `${BACKEND_URL}/legal/terms`,
  deleteAccount: `${BACKEND_URL}/legal/delete-account`,
  support: `${BACKEND_URL}/legal/support`,
};

export const APP_VERSION = Constants.expoConfig?.version ?? "1.0.0";

/** Store build number — versionCode on Android, buildNumber on iOS. */
export const BUILD_NUMBER =
  Constants.expoConfig?.ios?.buildNumber ??
  (Constants.expoConfig?.android?.versionCode != null
    ? String(Constants.expoConfig.android.versionCode)
    : null);

export const VERSION_LABEL = BUILD_NUMBER ? `${APP_VERSION} (${BUILD_NUMBER})` : APP_VERSION;
