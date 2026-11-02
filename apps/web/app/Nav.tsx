"use client";

import Link from "next/link";
import { useAuth } from "@/lib/auth";

export default function Nav() {
  const { user, ready, signOut } = useAuth();
  return (
    <nav className="nav">
      {ready && user && (
        <>
          <Link href="/saved">Saved searches</Link>
          <span className="muted">{user.email}</span>
          <button className="link" onClick={signOut}>Sign out</button>
        </>
      )}
      {ready && !user && <Link href="/login">Sign in</Link>}
    </nav>
  );
}
