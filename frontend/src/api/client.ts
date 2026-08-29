import { storage } from "@/src/utils/storage";
import { BACKEND_URL } from "@/src/config/app";
import { deviceHeader } from "@/src/utils/device";

const BASE = `${BACKEND_URL}/api`;
const TOKEN_KEY = "psybooks_token";

let memToken: string | null = null;

export async function setToken(token: string | null) {
  memToken = token;
  if (token) await storage.secureSet(TOKEN_KEY, token);
  else await storage.secureRemove(TOKEN_KEY);
}

export async function loadToken(): Promise<string | null> {
  if (memToken) return memToken;
  const t = await storage.secureGet<string>(TOKEN_KEY, "");
  memToken = t && t.length > 0 ? t : null;
  return memToken;
}

/**
 * HMRC requires fraud prevention headers describing the originating
 * device on every Making Tax Digital call. Only those routes pay the
 * cost of collecting them.
 */
async function requestWithDevice(path: string, options: RequestInit = {}) {
  return request(path, { ...options, headers: { ...(options.headers as any), ...(await deviceHeader()) } });
}

async function request(path: string, options: RequestInit = {}) {
  if (!BACKEND_URL) {
    // A release build without EXPO_PUBLIC_BACKEND_URL would fail with an opaque
    // network error; fail loudly instead so it is caught before submission.
    throw new Error("This build has no API address configured. Please reinstall from the store.");
  }
  const token = await loadToken();
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(options.headers as Record<string, string>),
  };
  if (token) headers.Authorization = `Bearer ${token}`;

  const res = await fetch(`${BASE}${path}`, { ...options, headers });
  const text = await res.text();
  let data: any = {};
  try {
    data = text ? JSON.parse(text) : {};
  } catch {
    data = {};
  }
  if (!res.ok) {
    throw new Error(data?.detail || `Request failed (${res.status})`);
  }
  return data;
}

export const api = {
  register: (body: any) => request("/auth/register", { method: "POST", body: JSON.stringify(body) }),
  login: (body: any) => request("/auth/login", { method: "POST", body: JSON.stringify(body) }),
  me: () => request("/auth/me"),
  updateProfile: (body: any) => request("/auth/profile", { method: "PUT", body: JSON.stringify(body) }),
  deleteAccount: () => request("/auth/account", { method: "DELETE" }),

  clients: () => request("/clients"),
  createClient: (body: any) => request("/clients", { method: "POST", body: JSON.stringify(body) }),
  updateClient: (id: string, body: any) => request(`/clients/${id}`, { method: "PUT", body: JSON.stringify(body) }),
  deleteClient: (id: string) => request(`/clients/${id}`, { method: "DELETE" }),

  invoices: () => request("/invoices"),
  createInvoice: (body: any) => request("/invoices", { method: "POST", body: JSON.stringify(body) }),
  updateInvoice: (id: string, body: any) => request(`/invoices/${id}`, { method: "PUT", body: JSON.stringify(body) }),
  deleteInvoice: (id: string) => request(`/invoices/${id}`, { method: "DELETE" }),

  expenseCategories: () => request("/expense-categories"),
  expenses: () => request("/expenses"),
  createExpense: (body: any) => request("/expenses", { method: "POST", body: JSON.stringify(body) }),
  updateExpense: (id: string, body: any) => request(`/expenses/${id}`, { method: "PUT", body: JSON.stringify(body) }),
  deleteExpense: (id: string) => request(`/expenses/${id}`, { method: "DELETE" }),

  summary: (start: string, end: string, group: string = "month") =>
    request(`/summary?start=${start}&end=${end}&group=${group}`),
  exportCsv: (start: string, end: string) => request(`/export/csv?start=${start}&end=${end}`),
  scanReceipt: (image_base64: string) => request("/expenses/scan", { method: "POST", body: JSON.stringify({ image_base64 }) }),
  companiesSearch: (q: string) => request(`/companies/search?q=${encodeURIComponent(q)}`),
  companyProfile: (num: string) => request(`/companies/${encodeURIComponent(num)}`),
};

export const hmrc = {
  status: () => requestWithDevice("/hmrc/status"),
  connect: () => request("/hmrc/connect", { method: "POST" }),
  disconnect: () => request("/hmrc/disconnect", { method: "POST" }),
  setNino: (nino: string) => request("/hmrc/nino", { method: "POST", body: JSON.stringify({ nino }) }),
  businesses: () => requestWithDevice("/hmrc/businesses"),
  setBusiness: (business_id: string) =>
    request("/hmrc/business", { method: "POST", body: JSON.stringify({ business_id }) }),
  obligations: (taxYear?: string) =>
    requestWithDevice(`/hmrc/obligations${taxYear ? `?tax_year=${taxYear}` : ""}`),
  quarterPreview: (taxYear: string, quarter: number) =>
    request(`/hmrc/quarter-preview?tax_year=${taxYear}&quarter=${quarter}`),
  submitQuarter: (tax_year: string, quarter: number) =>
    requestWithDevice("/hmrc/submit-quarter", {
      method: "POST",
      body: JSON.stringify({ tax_year, quarter, confirm: true }),
    }),
  submissions: () => request("/hmrc/submissions"),
};

export async function receiptUrl(path: string): Promise<string> {
  const token = await loadToken();
  return `${BASE}/files/${path}?token=${token || ""}`;
}
