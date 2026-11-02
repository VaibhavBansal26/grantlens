"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { API, Deadline, Facets, getJson, money, ymd } from "@/lib/api";
import { useAuth } from "@/lib/auth";

const WEEKDAYS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];

export default function DeadlinesPage() {
  const { user } = useAuth();
  const now = new Date();
  const [cursor, setCursor] = useState(new Date(now.getFullYear(), now.getMonth(), 1));
  const [scope, setScope] = useState<"all" | "saved">("all");
  const [agency, setAgency] = useState("");
  const [facets, setFacets] = useState<Facets | null>(null);
  const [items, setItems] = useState<Deadline[] | null>(null);
  const [truncated, setTruncated] = useState(false);
  const [error, setError] = useState("");

  // The grid always shows whole weeks, so the window covers the leading/trailing days too.
  const first = new Date(cursor.getFullYear(), cursor.getMonth(), 1);
  const start = new Date(first.getFullYear(), first.getMonth(), 1 - first.getDay());
  const last = new Date(cursor.getFullYear(), cursor.getMonth() + 1, 0);
  const end = new Date(last.getFullYear(), last.getMonth(), last.getDate() + (6 - last.getDay()));

  const query = useMemo(() => {
    const u = new URLSearchParams({ start: ymd(start), end: ymd(end) });
    if (scope === "saved") u.set("scope", "saved");
    if (agency && scope === "all") u.set("agency", agency);
    return u.toString();
  }, [cursor, scope, agency]);

  useEffect(() => { getJson<Facets>(`${API}/facets`).then(setFacets).catch(() => {}); }, []);

  useEffect(() => {
    setItems(null);
    setError("");
    getJson<{ deadlines: Deadline[]; truncated: boolean }>(`${API}/deadlines?${query}`)
      .then((r) => { setItems(r.deadlines); setTruncated(r.truncated); })
      .catch((e) => setError((e as Error).message));
  }, [query]);

  const byDay = useMemo(() => {
    const m = new Map<string, Deadline[]>();
    items?.forEach((d) => m.set(d.close_date, [...(m.get(d.close_date) ?? []), d]));
    return m;
  }, [items]);

  const days: Date[] = [];
  for (let d = new Date(start); d <= end; d = new Date(d.getFullYear(), d.getMonth(), d.getDate() + 1)) days.push(d);
  const today = ymd(now);
  const monthLabel = cursor.toLocaleDateString("en-US", { month: "long", year: "numeric" });
  const move = (n: number) => setCursor(new Date(cursor.getFullYear(), cursor.getMonth() + n, 1));
  const inMonth = items?.filter((d) => d.close_date >= ymd(first) && d.close_date <= ymd(last)) ?? [];

  return (
    <>
      <h1>Deadlines</h1>
      <div className="filters">
        <label>Show
          <select value={scope} onChange={(e) => setScope(e.target.value as "all" | "saved")}>
            <option value="all">All open grants</option>
            <option value="saved" disabled={!user}>{user ? "Matches from my saved searches" : "My saved searches (sign in)"}</option>
          </select>
        </label>
        {scope === "all" && (
          <label>Agency
            <select value={agency} onChange={(e) => setAgency(e.target.value)}>
              <option value="">Any</option>
              {facets?.agencies.map((a) => <option key={a.value} value={a.value}>{a.value}</option>)}
            </select>
          </label>
        )}
        <a className="download" href={`${API}/deadlines.ics?${query}`}>Download calendar (.ics)</a>
      </div>

      <div className="calnav">
        <button className="primary" onClick={() => move(-1)} aria-label="Previous month">←</button>
        <h2>{monthLabel}</h2>
        <button className="primary" onClick={() => move(1)} aria-label="Next month">→</button>
        <button className="link" onClick={() => setCursor(new Date(now.getFullYear(), now.getMonth(), 1))}>Today</button>
      </div>

      {error && <p className="error">{error}</p>}
      {truncated && <p className="muted">Showing the first 500 deadlines; narrow by agency to see the rest.</p>}

      <div className="calgrid" role="grid" aria-label={`Deadlines for ${monthLabel}`}>
        {WEEKDAYS.map((w) => <div className="calhead" key={w}>{w}</div>)}
        {days.map((d) => {
          const key = ymd(d);
          const list = byDay.get(key) ?? [];
          return (
            <div key={key} role="gridcell" className={`calcell${d.getMonth() !== cursor.getMonth() ? " other" : ""}${key === today ? " today" : ""}`}>
              <span className="daynum">{d.getDate()}</span>
              {list.slice(0, 3).map((x) => (
                <Link key={x.id} href={`/opportunity/${x.id}`} className="calitem" title={x.title}>{x.title}</Link>
              ))}
              {list.length > 3 && <span className="muted more">+{list.length - 3} more</span>}
            </div>
          );
        })}
      </div>

      <h2>This month ({items ? inMonth.length : "…"})</h2>
      {items && inMonth.length === 0 && <p className="empty">No deadlines this month for this view.</p>}
      {Array.from(byDay.entries()).filter(([k]) => k >= ymd(first) && k <= ymd(last)).map(([k, list]) => (
        <section key={k} className="agenda">
          <h3>{new Date(`${k}T00:00:00`).toLocaleDateString("en-US", { weekday: "long", month: "short", day: "numeric" })}</h3>
          {list.map((x) => (
            <p key={x.id}>
              <Link href={`/opportunity/${x.id}`}>{x.title}</Link>
              <span className="muted"> · {x.agency ?? "unknown agency"}{x.amount_max != null ? ` · up to ${money(x.amount_max)}` : ""}</span>
            </p>
          ))}
        </section>
      ))}
    </>
  );
}
