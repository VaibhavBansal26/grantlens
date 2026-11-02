"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import { API, Detail, getJson, money } from "@/lib/api";
import WatchButton from "../../WatchButton";

export default function OpportunityPage() {
  const { id } = useParams<{ id: string }>();
  const [d, setD] = useState<Detail | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    getJson<Detail>(`${API}/opportunities/${id}`).then(setD).catch(() => setError("Opportunity not found."));
  }, [id]);

  if (error) return <p className="error">{error} <Link href="/">Back to search</Link></p>;
  if (!d) return <p className="muted">Loading…</p>;

  return (
    <article>
      <p><Link href="/">← Back to search</Link></p>
      <h1>{d.title}</h1>
      <div className="meta">
        {d.status && <span className={`badge ${d.status}`}>{d.status}</span>}
        {d.number && <span>{d.number}</span>}
      </div>
      <div className="actions">
        <WatchButton id={d.id} />
        {d.url && <a href={d.url} target="_blank" rel="noreferrer">View on source site ↗</a>}
        {d.close_date && <a href={`${API}/opportunities/${d.id}.ics`}>Add deadline to calendar</a>}
      </div>
      <dl>
        <dt>Agency</dt><dd>{d.agency ?? "n/a"}</dd>
        <dt>Opens</dt><dd>{d.open_date ?? "n/a"}</dd>
        <dt>Closes</dt><dd>{d.close_date ?? "no close date listed"}</dd>
        <dt>Award range</dt><dd>{money(d.amount_min)} – {money(d.amount_max)}</dd>
        <dt>Funding type</dt><dd>{d.funding_instruments.join(", ") || "n/a"}</dd>
        <dt>Categories</dt><dd>{d.categories.join(", ") || "n/a"}</dd>
        <dt>Who can apply</dt><dd>{d.eligibility.join("; ") || "n/a"}</dd>
      </dl>
      <h2>Description</h2>
      <p style={{ whiteSpace: "pre-wrap" }}>{d.abstract ?? "No description available."}</p>
    </article>
  );
}
