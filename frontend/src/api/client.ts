import { storage } from "@/src/utils/storage";

const BASE = `${process.env.EXPO_PUBLIC_BACKEND_URL}/api`;
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

async function request(path: string, options: RequestInit = {}) {
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

  clients: () => request("/clients"),
  createClient: (body: any) => request("/clients", { method: "POST", body: JSON.stringify(body) }),
  updateClient: (id: string, body: any) => request(`/clients/${id}`, { method: "PUT", body: JSON.stringify(body) }),
  deleteClient: (id: string) => request(`/clients/${id}`, { method: "DELETE" }),

  invoices: () => request("/invoices"),
  createInvoice: (body: any) => request("/invoices", { method: "POST", body: JSON.stringify(body) }),
  updateInvoice: (id: string, body: any) => request(`/invoices/${id}`, { method: "PUT", body: JSON.stringify(body) }),
  deleteInvoice: (id: string) => request(`/invoices/${id}`, { method: "DELETE" }),
  emailInvoice: (id: string) => request(`/invoices/${id}/email`, { method: "POST" }),

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

export async function receiptUrl(path: string): Promise<string> {
  const token = await loadToken();
  return `${BASE}/files/${path}?token=${token || ""}`;
}
