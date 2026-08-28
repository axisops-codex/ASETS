// UK money + date helpers (GBP, fiscal year 6 Apr – 5 Apr)

export function gbp(n: number, decimals = 2): string {
  const val = Number.isFinite(n) ? n : 0;
  const fixed = Math.abs(val).toFixed(decimals);
  const [intPart, decPart] = fixed.split(".");
  const withSep = intPart.replace(/\B(?=(\d{3})+(?!\d))/g, ",");
  const sign = val < 0 ? "-" : "";
  return `${sign}£${withSep}${decPart ? "." + decPart : ""}`;
}

export function gbpShort(n: number): string {
  const val = Number.isFinite(n) ? n : 0;
  if (Math.abs(val) >= 1000) return gbp(val, 0);
  return gbp(val, 2);
}

export function pad(n: number): string {
  return n < 10 ? `0${n}` : `${n}`;
}

export function toISODate(d: Date): string {
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
}

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

export function prettyDate(iso?: string | null): string {
  if (!iso) return "—";
  const [y, m, d] = iso.slice(0, 10).split("-").map(Number);
  if (!y || !m || !d) return iso;
  return `${d} ${MONTHS[m - 1]} ${y}`;
}

export function prettyMonth(ym: string): string {
  const [y, m] = ym.split("-").map(Number);
  return `${MONTHS[(m || 1) - 1]} ${String(y).slice(2)}`;
}

// UK fiscal year: 6 April -> 5 April
export function fiscalYearRange(reference = new Date()): { start: string; end: string; label: string } {
  const y = reference.getFullYear();
  const m = reference.getMonth() + 1; // 1-12
  const d = reference.getDate();
  const afterApril6 = m > 4 || (m === 4 && d >= 6);
  const startYear = afterApril6 ? y : y - 1;
  return {
    start: `${startYear}-04-06`,
    end: `${startYear + 1}-04-05`,
    label: `${startYear}/${String(startYear + 1).slice(2)}`,
  };
}

export function fiscalYearByStartYear(startYear: number) {
  return {
    start: `${startYear}-04-06`,
    end: `${startYear + 1}-04-05`,
    label: `${startYear}/${String(startYear + 1).slice(2)}`,
  };
}

export type Period = "day" | "week" | "month" | "year";

export function periodRange(period: Period, ref = new Date()): { start: string; end: string; label: string; group: string } {
  if (period === "day") {
    const s = toISODate(ref);
    return { start: s, end: s, label: "Today", group: "day" };
  }
  if (period === "week") {
    const day = (ref.getDay() + 6) % 7; // Monday = 0
    const monday = new Date(ref);
    monday.setDate(ref.getDate() - day);
    const sunday = new Date(monday);
    sunday.setDate(monday.getDate() + 6);
    return { start: toISODate(monday), end: toISODate(sunday), label: "This week", group: "day" };
  }
  if (period === "month") {
    const first = new Date(ref.getFullYear(), ref.getMonth(), 1);
    const last = new Date(ref.getFullYear(), ref.getMonth() + 1, 0);
    return { start: toISODate(first), end: toISODate(last), label: MONTHS[ref.getMonth()] + " " + ref.getFullYear(), group: "day" };
  }
  const fy = fiscalYearRange(ref);
  return { start: fy.start, end: fy.end, label: "Tax year " + fy.label, group: "month" };
}

export function prettyBucket(key: string, group: string): string {
  if (group === "day") {
    const [y, m, d] = key.split("-").map(Number);
    return `${d} ${MONTHS[(m || 1) - 1]}`;
  }
  return prettyMonth(key);
}
