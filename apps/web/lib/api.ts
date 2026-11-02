export const API = "/api";

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

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
  }
}

async function parse<T>(res: Response): Promise<T> {
  if (res.status === 204) return undefined as T;
  const body = await res.json().catch(() => ({}));
  if (!res.ok) throw new ApiError(res.status, body.error ?? `${res.status} ${res.statusText}`);
  return body as T;
}

export const getJson = <T,>(url: string): Promise<T> => fetch(url).then((r) => parse<T>(r));

export const sendJson = <T,>(method: "POST" | "PUT" | "PATCH" | "DELETE", url: string, body?: unknown): Promise<T> =>
  fetch(url, {
    method,
    headers: body === undefined ? undefined : { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  }).then((r) => parse<T>(r));

export type User = { id: number; email: string; reminders?: boolean };

export type Saved = {
  id: number;
  name: string;
  params: Record<string, string[]>;
  alerts: boolean;
  created_at: string;
};

/** Saved-search params ({name: [values]}) -> the URL of the search page that reruns it. */
export const savedHref = (s: Saved): string => {
  const u = new URLSearchParams();
  Object.entries(s.params).forEach(([k, vs]) => vs.forEach((v) => u.append(k, v)));
  return `/?${u}`;
};

export const money = (n: number | null) =>
  n == null ? "n/a" : n.toLocaleString("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 0 });

export type Deadline = {
  id: number;
  title: string;
  agency: string | null;
  status: string | null;
  close_date: string;
  amount_max: number | null;
};

/** Local calendar date as YYYY-MM-DD (toISOString would shift it by the UTC offset). */
export const ymd = (d: Date): string =>
  `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;

export type Watched = {
  id: number;
  title: string;
  agency: string | null;
  status: string | null;
  close_date: string | null;
  days_left: number | null;
  amount_max: number | null;
  added_at: string;
};

export type Paper = {
  id: string;
  title: string;
  year: number | null;
  cited_by: number;
  doi: string | null;
  abstract: string;
  authors: string[];
  venue: string | null;
  url: string | null;
};

export type Match = Hit & { closest_paper: string | null };

export type MatchResponse = {
  profile: { name: string | null; papers: Paper[]; text_used: string };
  results: Match[];
};
