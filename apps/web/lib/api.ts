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

export type User = { id: number; email: string; reminders?: boolean; email_verified?: boolean };

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
  // A saved search without a status filter means "every status". The search page now defaults to open
  // grants, so spell it out; otherwise opening an older saved search would quietly show different results.
  if (!s.params.status?.length) ["posted", "forecasted", "closed", "archived"].forEach((v) => u.append("status", v));
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

export type Doc = { id: number; title: string; pages: number; created_at: string; expires_at?: string | null };

export type Answer = {
  answer: string;
  supported: boolean;
  removed_citations: number;
  citations: { n: number; page: number; quote: string }[];
};

export async function uploadFile<T>(url: string, file: File): Promise<T> {
  const body = new FormData();
  body.append("file", file);
  return fetch(url, { method: "POST", body }).then((r) => parse<T>(r));
}

export type FitResult = {
  summary: string;
  eligibility: { requirement: string; requirement_quote: string; status: "met" | "unclear" | "not_met"; researcher_quote: string; note: string }[];
  strengths: string[];
  gaps: string[];
  aims: { aim: string; rationale: string; papers: string[] }[];
  papers: { id: string; title: string; year: number | null; url: string | null; authors: string[] }[];
  downgraded: number;
  dropped_requirements: number;
  removed_citations: number;
  literature_available: boolean;
  grant_closed: boolean;
};

export type ReviewPaper = {
  id: string;
  title: string;
  year: number | null;
  authors: string[];
  venue: string | null;
  url: string | null;
  cited_by: number;
  theme: number;
  annotation: string;
  evidence_quote: string;
};

export type ReviewResult = {
  id: number;
  topic: string;
  created_at: string;
  themes: { title: string; summary: string; papers: string[] }[];
  papers: ReviewPaper[];
  open_questions: string[];
  skipped_no_abstract: number;
  unverified_annotations: number;
  removed_citations: number;
  literature_available: boolean;
};

export type ReviewSummary = { id: number; topic: string; created_at: string; papers: number };
