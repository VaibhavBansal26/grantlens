"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { API, sendJson } from "@/lib/api";
import { useAuth } from "@/lib/auth";

export default function AccountPage() {
  const { user, ready, signOut } = useAuth();
  const router = useRouter();
  const [confirming, setConfirming] = useState(false);
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    if (ready && !user) router.replace("/login?next=/account");
  }, [ready, user, router]);

  async function remove(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      await sendJson("DELETE", `${API}/auth/account`, { password });
      await signOut();
      router.replace("/");
    } catch (err) {
      setError((err as Error).message);
      setBusy(false);
    }
  }

  if (!user) return <p className="muted">Loading…</p>;
  return (
    <section className="authform">
      <h1>Your account</h1>
      <p>Signed in as <strong>{user.email}</strong>.</p>
      <h2>Delete my account</h2>
      <p className="muted">This permanently deletes your account and everything tied to it: saved searches, watchlist, uploaded document text, reviews, alert settings and AI usage records. It cannot be undone. Shared grant data is not affected.</p>
      {!confirming ? (
        <button className="primary" onClick={() => setConfirming(true)}>Delete my account…</button>
      ) : (
        <form onSubmit={remove} className="authform">
          <label>Type your password to confirm
            <input type="password" value={password} onChange={(e) => setPassword(e.target.value)} autoComplete="current-password" required />
          </label>
          {error && <p className="error" role="alert">{error}</p>}
          <button className="primary" disabled={busy || !password}>{busy ? "Deleting…" : "Permanently delete everything"}</button>
          <button type="button" className="link" onClick={() => { setConfirming(false); setPassword(""); setError(""); }}>Cancel</button>
        </form>
      )}
    </section>
  );
}
