"use client";

import Link from "next/link";
import { useState } from "react";
import { API, sendJson } from "@/lib/api";

export default function ForgotPage() {
  const [email, setEmail] = useState("");
  const [state, setState] = useState<"ask" | "busy" | "sent">("ask");
  const [error, setError] = useState("");

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setState("busy");
    setError("");
    try {
      await sendJson("POST", `${API}/auth/forgot`, { email });
      setState("sent");
    } catch (err) {
      setError((err as Error).message);
      setState("ask");
    }
  }

  if (state === "sent") {
    return (
      <section className="authform">
        <h1>Check your email</h1>
        <p>If that address has a GrantLens account, we have sent a link to choose a new password. It works for one hour.</p>
        <p><Link href="/login">Back to sign in</Link></p>
      </section>
    );
  }
  return (
    <form className="authform" onSubmit={submit}>
      <h1>Reset your password</h1>
      <label>Email
        <input type="email" value={email} onChange={(e) => setEmail(e.target.value)} autoComplete="email" required />
      </label>
      {error && <p className="error" role="alert">{error}</p>}
      <button className="primary" disabled={state === "busy" || !email.trim()}>Send reset link</button>
    </form>
  );
}
