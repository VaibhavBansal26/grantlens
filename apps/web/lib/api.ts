export const API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:5055";

export type Hit = {
  id: number;
  title: string;
  agency: string | null;
  status: string | null;
  close_date: string | null;
  url: string | null;
  snippet: string;
  amount_max: number | null;
  score: number;
  ranks: { bm25?: number; dense?: number };
};

export type Detail = {
  id: number;
  number: string | null;
  title: string;
  abstract: string | null;
  agency: string | null;
  status: string | null;
  url: string | null;
  categories: string[];
  eligibility: string[];
  funding_instruments: string[];
  amount_min: number | null;
  amount_max: number | null;
  open_date: string | null;
  close_date: string | null;
};

export type Facets = {
  statuses: { value: string; count: number }[];
  agencies: { value: string; count: number }[];
};

export type SearchParams = {
  q: string;
  mode: "hybrid" | "bm25" | "dense";
  status: string[];
  agency: string;
  closesAfter: string;
  minAmount: string;
};

export function searchUrl(p: SearchParams): string {
  const u = new URLSearchParams({ q: p.q, mode: p.mode, k: "20" });
  p.status.forEach((s) => u.append("status", s));
  if (p.agency) u.set("agency", p.agency);
  if (p.closesAfter) u.set("closes_after", p.closesAfter);
  if (p.minAmount) u.set("min_amount", p.minAmount);
  return `${API}/search?${u}`;
}

export async function getJson<T>(url: string): Promise<T> {
  const res = await fetch(url);
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
  return res.json();
}

export const money = (n: number | null) =>
  n == null ? "n/a" : n.toLocaleString("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 0 });
