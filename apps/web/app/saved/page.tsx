"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { API, ApiError, Hit, Saved, getJson, savedHref, sendJson } from "@/lib/api";
import { useAuth } from "@/lib/auth";

type Row = Saved & { fresh: Hit[] | null };

export default function SavedPage() {
  const { user, ready } = useAuth();
  const router = useRouter();
  const [rows, setRows] = useState<Row[] | null>(null);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  useEffect(() => {
    if (!ready) return;
    if (!user) { router.replace("/login?next=/saved"); return; }
    getJson<{ saved: Saved[] }>(`${API}/saved-searches`)
      .then(async ({ saved }) => {
        setRows(saved.map((s) => ({ ...s, fresh: null })));
        saved.forEach((s) =>
          getJson<{ results: Hit[] }>(`${API}/saved-searches/${s.id}/new`)
            .then((r) => setRows((cur) => cur && cur.map((x) => (x.id === s.id ? { ...x, fresh: r.results } : x))))
            .catch(() => {}),
        );
      })
      .catch((e) => setError((e as Error).message));
  }, [ready, user, router]);

  async function remove(id: number) {
    await sendJson("DELETE", `${API}/saved-searches/${id}`);
    setRows((cur) => cur && cur.filter((r) => r.id !== id));
  }

  async function setAlerts(id: number, on: boolean) {
    setNotice("");
    setRows((cur) => cur && cur.map((r) => (r.id === id ? { ...r, alerts: on } : r)));
    try {
      await sendJson("PATCH", `${API}/saved-searches/${id}`, { alerts: on });
    } catch (e) {
      setRows((cur) => cur && cur.map((r) => (r.id === id ? { ...r, alerts: !on } : r)));
      if (e instanceof ApiError && e.status === 403) setNotice(e.message);
      else setError("Could not change the email setting. Try again.");
    }
  }

  async function markSeen(id: number) {
    await sendJson("POST", `${API}/saved-searches/${id}/seen`);
    setRows((cur) => cur && cur.map((r) => (r.id === id ? { ...r, fresh: [] } : r)));
  }

  if (error) return <p className="error">{error}</p>;
  if (!rows) return <p className="muted">Loading…</p>;

  return (
    <>
      <h1>Saved searches</h1>
      {notice && <p className="error" role="alert">{notice}</p>}
      {rows.length === 0 && <p className="empty">Nothing saved yet. Run a search and choose “Save this search”.</p>}
      {rows.map((s) => (
        <article className="result" key={s.id}>
          <h3><Link href={savedHref(s)}>{s.name}</Link></h3>
          <div className="meta">
            <span>“{s.params.q?.[0]}”</span>
            <span>{s.params.status?.length ? s.params.status.join(", ") : "all statuses"}</span>
            {s.fresh === null ? <span>checking for new grants…</span>
              : s.fresh.length > 0 ? <span className="badge posted">{s.fresh.length} new since you last looked</span>
              : <span>no new matches</span>}
          </div>
          {s.fresh && s.fresh.length > 0 && (
            <ul>{s.fresh.slice(0, 5).map((h) => <li key={h.id}><Link href={`/opportunity/${h.id}`}>{h.title}</Link></li>)}</ul>
          )}
          <label className="check">
            <input type="checkbox" checked={s.alerts} onChange={(e) => setAlerts(s.id, e.target.checked)} />
            Email me new matches
          </label>
          <div className="actions">
            {s.fresh && s.fresh.length > 0 && <button className="link" onClick={() => markSeen(s.id)}>Mark as seen</button>}
            <button className="link" onClick={() => remove(s.id)}>Delete</button>
          </div>
        </article>
      ))}
    </>
  );
}
