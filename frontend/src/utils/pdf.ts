import * as Print from "expo-print";
import * as Sharing from "expo-sharing";
import { Platform } from "react-native";
import { gbp, prettyDate } from "./format";

type Item = { description: string; quantity: number; unit_price: number };

type InvoiceForPdf = {
  number: string;
  issue_date: string;
  due_date?: string | null;
  items: Item[];
  notes?: string;
  total: number;
  status: string;
  client_name?: string;
};

type Business = {
  name?: string;
  business_name?: string;
  email?: string;
  address?: string;
  utr?: string;
};

type ClientInfo = { name?: string; email?: string; address?: string };

function invoiceHtml(inv: InvoiceForPdf, biz: Business, client: ClientInfo): string {
  const rows = inv.items
    .map(
      (it) => `<tr>
        <td>${escapeHtml(it.description)}</td>
        <td class="num">${it.quantity}</td>
        <td class="num">${gbp(it.unit_price)}</td>
        <td class="num">${gbp((it.quantity || 0) * (it.unit_price || 0))}</td>
      </tr>`
    )
    .join("");

  const bizName = biz.business_name || biz.name || "My Practice";

  return `<!DOCTYPE html><html><head><meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <style>
    * { box-sizing: border-box; }
    body { font-family: -apple-system, Helvetica, Arial, sans-serif; color: #1A1C1A; padding: 40px; }
    .header { display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 32px; }
    .brand { font-size: 22px; font-weight: 700; color: #5F7161; }
    h1 { font-size: 30px; margin: 0; letter-spacing: -0.5px; }
    .muted { color: #6b6f6b; font-size: 13px; line-height: 1.5; }
    .grid { display: flex; justify-content: space-between; margin: 24px 0; gap: 24px; }
    .block { flex: 1; }
    .label { text-transform: uppercase; font-size: 11px; letter-spacing: 1px; color: #9a9e9a; margin-bottom: 6px; }
    table { width: 100%; border-collapse: collapse; margin-top: 12px; }
    th { text-align: left; font-size: 11px; text-transform: uppercase; letter-spacing: 1px; color: #9a9e9a; padding: 10px 8px; border-bottom: 2px solid #E5E5E3; }
    td { padding: 12px 8px; border-bottom: 1px solid #eee; font-size: 14px; }
    .num { text-align: right; }
    .totals { margin-top: 24px; margin-left: auto; width: 260px; }
    .totals .row { display: flex; justify-content: space-between; padding: 8px 0; }
    .totals .grand { border-top: 2px solid #1A1C1A; margin-top: 8px; padding-top: 12px; font-size: 20px; font-weight: 700; }
    .note { margin-top: 32px; padding: 16px; background: #F0F0EE; border-radius: 12px; font-size: 13px; color: #4A4D4A; }
    .footer { margin-top: 40px; font-size: 11px; color: #9a9e9a; text-align: center; }
    .vat { font-size: 12px; color: #6b6f6b; margin-top: 4px; }
  </style></head>
  <body>
    <div class="header">
      <div>
        <div class="brand">${escapeHtml(bizName)}</div>
        <div class="muted">${nl2br(escapeHtml(biz.address || ""))}</div>
        ${biz.email ? `<div class="muted">${escapeHtml(biz.email)}</div>` : ""}
        ${biz.utr ? `<div class="muted">UTR: ${escapeHtml(biz.utr)}</div>` : ""}
      </div>
      <div style="text-align:right;">
        <h1>INVOICE</h1>
        <div class="muted">${escapeHtml(inv.number)}</div>
      </div>
    </div>

    <div class="grid">
      <div class="block">
        <div class="label">Billed to</div>
        <div style="font-weight:600;">${escapeHtml(client.name || inv.client_name || "")}</div>
        <div class="muted">${nl2br(escapeHtml(client.address || ""))}</div>
        ${client.email ? `<div class="muted">${escapeHtml(client.email)}</div>` : ""}
      </div>
      <div class="block" style="text-align:right;">
        <div class="label">Issue date</div>
        <div>${prettyDate(inv.issue_date)}</div>
        ${inv.due_date ? `<div class="label" style="margin-top:12px;">Due date</div><div>${prettyDate(inv.due_date)}</div>` : ""}
      </div>
    </div>

    <table>
      <thead><tr><th>Description</th><th class="num">Qty</th><th class="num">Rate</th><th class="num">Amount</th></tr></thead>
      <tbody>${rows}</tbody>
    </table>

    <div class="totals">
      <div class="row"><span>Subtotal</span><span>${gbp(inv.total)}</span></div>
      <div class="row"><span>VAT</span><span>£0.00</span></div>
      <div class="row grand"><span>Total</span><span>${gbp(inv.total)}</span></div>
    </div>
    <div class="vat">No VAT charged — exempt healthcare services.</div>

    ${inv.notes ? `<div class="note">${nl2br(escapeHtml(inv.notes))}</div>` : ""}

    <div class="footer">Generated with PsyBooks</div>
  </body></html>`;
}

export async function shareInvoicePdf(inv: InvoiceForPdf, biz: Business, client: ClientInfo) {
  const html = invoiceHtml(inv, biz, client);
  const { uri } = await Print.printToFileAsync({ html });
  if (Platform.OS === "web") {
    await Print.printAsync({ html });
    return;
  }
  const canShare = await Sharing.isAvailableAsync();
  if (canShare) {
    await Sharing.shareAsync(uri, { mimeType: "application/pdf", dialogTitle: `Share ${inv.number}`, UTI: "com.adobe.pdf" });
  }
}

// ---- Tax report PDF ----
type TaxData = {
  sales: number;
  expenses: number;
  profit: number;
  personal_allowance: number;
  taxable_income: number;
  bands: { label: string; amount: number; tax: number }[];
  income_tax: number;
  national_insurance: number;
  total_due: number;
  take_home: number;
};

export function taxReportText(tax: TaxData, periodLabel: string): string {
  const lines = [
    `HMRC Estimate — ${periodLabel}`,
    ``,
    `Total sales:            ${gbp(tax.sales)}`,
    `Allowable expenses:   - ${gbp(tax.expenses)}`,
    `Taxable profit:         ${gbp(tax.profit)}`,
    `Personal allowance:     ${gbp(tax.personal_allowance)}`,
    `Income taxed:           ${gbp(tax.taxable_income)}`,
    ...tax.bands.map((b) => `  ${b.label}: ${gbp(b.amount)} -> ${gbp(b.tax)}`),
    `Income Tax:             ${gbp(tax.income_tax)}`,
    `National Insurance:     ${gbp(tax.national_insurance)}`,
    `Estimated tax to pay:   ${gbp(tax.total_due)}`,
    `Take home:              ${gbp(tax.take_home)}`,
    ``,
    `Estimate only. No VAT (exempt healthcare). Based on 2024/25 rates.`,
  ];
  return lines.join("\n");
}

export async function shareTaxPdf(tax: TaxData, periodLabel: string, biz: Business) {
  const bandRows = tax.bands
    .map((b) => `<tr><td>${escapeHtml(b.label)}</td><td class="num">${gbp(b.amount)}</td><td class="num">${gbp(b.tax)}</td></tr>`)
    .join("");
  const html = `<!DOCTYPE html><html><head><meta charset="utf-8" />
  <style>
    body { font-family: -apple-system, Helvetica, Arial, sans-serif; color: #1A1C1A; padding: 44px; }
    .brand { font-size: 20px; font-weight: 700; color: #5F7161; }
    h1 { font-size: 28px; margin: 4px 0 2px; letter-spacing: -0.5px; }
    .muted { color: #9a9e9a; font-size: 13px; }
    .receipt { margin-top: 28px; border: 1px solid #E5E5E3; border-radius: 16px; padding: 24px; max-width: 460px; }
    .line { display: flex; justify-content: space-between; padding: 11px 0; border-bottom: 1px dashed #E5E5E3; font-size: 15px; }
    .line.strong { font-weight: 700; border-bottom: 2px solid #1A1C1A; }
    .line.big { font-size: 22px; font-weight: 700; color: #5F7161; border: none; padding-top: 16px; }
    table { width: 100%; border-collapse: collapse; margin: 14px 0; }
    th { text-align:left; font-size:11px; text-transform:uppercase; letter-spacing:1px; color:#9a9e9a; padding:8px 4px; border-bottom:1px solid #E5E5E3;}
    td { padding: 8px 4px; font-size: 13px; }
    .num { text-align: right; }
    .footer { margin-top: 24px; font-size: 11px; color: #9a9e9a; }
  </style></head><body>
    <div class="brand">${escapeHtml(biz.business_name || biz.name || "PsyBooks")}</div>
    <h1>HMRC Tax Estimate</h1>
    <div class="muted">${escapeHtml(periodLabel)}</div>
    <div class="receipt">
      <div class="line"><span>Total sales</span><span>${gbp(tax.sales)}</span></div>
      <div class="line"><span>Less allowable expenses</span><span>- ${gbp(tax.expenses)}</span></div>
      <div class="line strong"><span>Taxable profit</span><span>${gbp(tax.profit)}</span></div>
      <div class="line"><span>Personal allowance</span><span>${gbp(tax.personal_allowance)}</span></div>
      <div class="line"><span>Income taxed</span><span>${gbp(tax.taxable_income)}</span></div>
      <table><thead><tr><th>Band</th><th class="num">Amount</th><th class="num">Tax</th></tr></thead>
      <tbody>${bandRows || '<tr><td colspan="3" class="muted">No income tax due</td></tr>'}</tbody></table>
      <div class="line"><span>Income Tax</span><span>${gbp(tax.income_tax)}</span></div>
      <div class="line strong"><span>National Insurance (Class 4)</span><span>${gbp(tax.national_insurance)}</span></div>
      <div class="line big"><span>Estimated tax to set aside</span><span>${gbp(tax.total_due)}</span></div>
      <div class="line"><span>Estimated take home</span><span>${gbp(tax.take_home)}</span></div>
    </div>
    <div class="footer">Estimate only, based on 2024/25 England &amp; NI rates. No VAT (exempt healthcare services). Not financial advice.</div>
  </body></html>`;
  const { uri } = await Print.printToFileAsync({ html });
  if (Platform.OS === "web") {
    await Print.printAsync({ html });
    return;
  }
  const canShare = await Sharing.isAvailableAsync();
  if (canShare) {
    await Sharing.shareAsync(uri, { mimeType: "application/pdf", dialogTitle: "Share tax estimate", UTI: "com.adobe.pdf" });
  }
}

function escapeHtml(s: string): string {
  return (s || "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function nl2br(s: string): string {
  return (s || "").replace(/\n/g, "<br/>");
}
