"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { API, Watched, getJson, money, sendJson } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import WatchButton from "../WatchButton";

function when(w: Watched): { text: string; tone: "" | "soon" | "closed" } {
  if (w.days_left === null) return { text: "no close date listed", tone: "" };
  if (w.days_left < 0) return { text: `closed ${-w.days_left} day${w.days_left === -1 ? "" : "s"} ago`, tone: "closed" };
  if (w.days_left === 0) return { text: "closes today", tone: "soon" };
  return { text: `closes in ${w.days_left} day${w.days_left === 1 ? "" : "s"} (${w.close_date})`, tone: w.days_left <= 14 ? "soon" : "" };
}

export default function WatchlistPage() {
  const { user, ready, updateUser } = useAuth();
  const router = useRouter();
  const [items, setItems] = useState<Watched[] | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!ready) return;
    if (!user) { router.replace("/login?next=/watchlist"); return; }
    getJson<{ items: Watched[] }>(`${API}/watchlist`).then((r) => setItems(r.items)).catch((e) => setError((e as Error).message));
  }, [ready, user, router]);

  async function setReminders(on: boolean) {
    updateUser({ reminders: on });
    try {
      await sendJson("PATCH", `${API}/auth/preferences`, { reminders: on });
    } catch {
      updateUser({ reminders: !on });
      setError("Could not change the email setting. Try again.");
    }
  }

  if (error) return <p className="error">{error}</p>;
  if (!items) return <p className="muted">Loading…</p>;

  return (
    <>
      <h1>Watchlist</h1>
      <label className="check">
        <input type="checkbox" checked={!!user?.reminders} onChange={(e) => setReminders(e.target.checked)} />
        Email me a week before, and again on the last day, when a watched grant is closing
      </label>
      {items.length === 0 && <p className="empty">No grants yet. Use “☆ Watch” on any grant to track its deadline here.</p>}
      {items.map((w) => {
        const t = when(w);
        return (
          <article className="result" key={w.id}>
            <h3><Link href={`/opportunity/${w.id}`}>{w.title}</Link></h3>
            <div className="meta">
              {w.status && <span className={`badge ${w.status}`}>{w.status}</span>}
              {w.agency && <span>{w.agency}</span>}
              <span className={`when ${t.tone}`}>{t.text}</span>
              {w.amount_max != null && <span>up to {money(w.amount_max)}</span>}
            </div>
            <div className="actions"><WatchButton id={w.id} /></div>
          </article>
        );
      })}
    </>
  );
}
