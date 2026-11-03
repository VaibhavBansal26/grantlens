"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { useAuth } from "@/lib/auth";

export default function LoginPage() {
  const { signIn } = useAuth();
  const router = useRouter();
  const [mode, setMode] = useState<"login" | "register">("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      await signIn(mode, email, password);
      const next = new URLSearchParams(window.location.search).get("next");
      router.push(next && next.startsWith("/") && !next.startsWith("//") ? next : "/saved");
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <form className="authform" onSubmit={submit}>
      <h1>{mode === "login" ? "Sign in" : "Create an account"}</h1>
      <label>Email
        <input type="email" value={email} onChange={(e) => setEmail(e.target.value)} autoComplete="email" required />
      </label>
      <label>Password
        <input
          type="password" value={password} onChange={(e) => setPassword(e.target.value)} minLength={mode === "register" ? 10 : undefined}
          autoComplete={mode === "login" ? "current-password" : "new-password"} required
        />
        {mode === "register" && <span className="muted">At least 10 characters.</span>}
      </label>
      {error && <p className="error" role="alert">{error}</p>}
      <button className="primary" disabled={busy}>{mode === "login" ? "Sign in" : "Create account"}</button>
      {mode === "login" && <p className="muted"><Link href="/forgot">Forgot your password?</Link></p>}
      <p className="muted">
        {mode === "login" ? "New here? " : "Already have an account? "}
        <button type="button" className="link" onClick={() => { setMode(mode === "login" ? "register" : "login"); setError(""); }}>
          {mode === "login" ? "Create an account" : "Sign in"}
        </button>
      </p>
    </form>
  );
}
