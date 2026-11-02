"use client";

import { createContext, useCallback, useContext, useEffect, useState } from "react";
import { API, Watched, getJson, sendJson } from "./api";
import { useAuth } from "./auth";

type Watch = {
  ids: Set<number>;
  toggle: (id: number) => Promise<void>;
};

const Ctx = createContext<Watch | null>(null);

export function WatchProvider({ children }: { children: React.ReactNode }) {
  const { user } = useAuth();
  const [ids, setIds] = useState<Set<number>>(new Set());

  useEffect(() => {
    if (!user) { setIds(new Set()); return; }
    getJson<{ items: Watched[] }>(`${API}/watchlist`)
      .then((r) => setIds(new Set(r.items.map((i) => i.id))))
      .catch(() => {});
  }, [user]);

  const toggle = useCallback(async (id: number) => {
    const watching = ids.has(id);
    // optimistic update; roll back if the server refuses
    setIds((cur) => { const n = new Set(cur); watching ? n.delete(id) : n.add(id); return n; });
    try {
      if (watching) await sendJson("DELETE", `${API}/watchlist/${id}`);
      else await sendJson("PUT", `${API}/watchlist/${id}`);
    } catch (e) {
      setIds((cur) => { const n = new Set(cur); watching ? n.add(id) : n.delete(id); return n; });
      throw e;
    }
  }, [ids]);

  return <Ctx.Provider value={{ ids, toggle }}>{children}</Ctx.Provider>;
}

export const useWatch = (): Watch => {
  const ctx = useContext(Ctx);
  if (!ctx) throw new Error("useWatch outside WatchProvider");
  return ctx;
};
