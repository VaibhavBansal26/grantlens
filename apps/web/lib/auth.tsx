"use client";

import { createContext, useCallback, useContext, useEffect, useState } from "react";
import { API, User, getJson, sendJson } from "./api";

type Auth = {
  user: User | null;
  ready: boolean;
  signIn: (mode: "login" | "register", email: string, password: string) => Promise<void>;
  signOut: () => Promise<void>;
  updateUser: (patch: Partial<User>) => void;
};

const Ctx = createContext<Auth | null>(null);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    getJson<{ user: User | null }>(`${API}/auth/me`)
      .then((r) => setUser(r.user))
      .catch(() => {})
      .finally(() => setReady(true));
  }, []);

  const signIn = useCallback(async (mode: "login" | "register", email: string, password: string) => {
    setUser(await sendJson<User>("POST", `${API}/auth/${mode}`, { email, password }));
  }, []);

  const signOut = useCallback(async () => {
    await sendJson("POST", `${API}/auth/logout`);
    setUser(null);
  }, []);

  const updateUser = useCallback((patch: Partial<User>) => setUser((u) => (u ? { ...u, ...patch } : u)), []);

  return <Ctx.Provider value={{ user, ready, signIn, signOut, updateUser }}>{children}</Ctx.Provider>;
}

export const useAuth = (): Auth => {
  const ctx = useContext(Ctx);
  if (!ctx) throw new Error("useAuth outside AuthProvider");
  return ctx;
};
