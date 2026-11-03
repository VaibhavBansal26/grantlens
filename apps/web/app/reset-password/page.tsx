"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { API, sendJson } from "@/lib/api";

export default function ResetPage() {
  const [token, setToken] = useState<string | null>(null);
  const [password, setPassword] = useState("");
  const [again, setAgain] = useState("");
  const [state, setState] = useState<"ask" | "busy" | "done">("ask");
  const [error, setError] = useState("");

  useEffect(() => { setToken(new URLSearchParams(window.location.search).get("token") ?? ""); }, []);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (password !== again) { setError("The two passwords do not match."); return; }
    setState("busy");
    setError("");
    try {
      await sendJson("POST", `${API}/auth/reset`, { token, password });
      setState("done");
    } catch (err) {
      setError((err as Error).message);
      setState("ask");
    }
  }

  if (token === null) return <p className="muted">Loading…</p>;
  if (!token) return <p className="error">This reset link is incomplete. <Link href="/forgot">Ask for a new one.</Link></p>;
  if (state === "done") {
    return (
      <section className="authform">
        <h1>Password changed</h1>
        <p>You have been signed out everywhere. <Link href="/login">Sign in with your new password.</Link></p>
      </section>
    );
  }
  return (
    <form className="authform" onSubmit={submit}>
      <h1>Choose a new password</h1>
      <label>New password
        <input type="password" value={password} onChange={(e) => setPassword(e.target.value)} minLength={10} autoComplete="new-password" required />
        <span className="muted">At least 10 characters.</span>
      </label>
      <label>Repeat it
        <input type="password" value={again} onChange={(e) => setAgain(e.target.value)} autoComplete="new-password" required />
      </label>
      {error && <p className="error" role="alert">{error} {error.includes("invalid or has expired") && <Link href="/forgot">Ask for a new link.</Link>}</p>}
      <button className="primary" disabled={state === "busy"}>Change password</button>
    </form>
  );
}
