"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { useAuth } from "@/lib/auth";
import { useWatch } from "@/lib/watch";

export default function WatchButton({ id }: { id: number }) {
  const { user, ready } = useAuth();
  const { ids, toggle } = useWatch();
  const router = useRouter();
  const [err, setErr] = useState("");
  const watching = ids.has(id);

  async function click() {
    if (!user) {
      router.push(`/login?next=${encodeURIComponent(window.location.pathname + window.location.search)}`);
      return;
    }
    setErr("");
    try { await toggle(id); } catch (e) { setErr((e as Error).message); }
  }

  if (!ready) return null;
  return (
    <>
      <button className={`watch${watching ? " on" : ""}`} onClick={click} aria-pressed={watching}>
        {watching ? "★ Watching" : "☆ Watch"}
      </button>
      {err && <span className="error"> {err}</span>}
    </>
  );
}
