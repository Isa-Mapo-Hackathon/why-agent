"use client";

import { useEffect, useState } from "react";

function fmt(ms: number): string {
  const s = Math.floor(ms / 1000);
  const m = Math.floor(s / 60);
  return m > 0 ? `${m}:${String(s % 60).padStart(2, "0")}` : `${s}s`;
}

export default function ElapsedTimer({ startedAt, stopped, finalMs }: { startedAt: number; stopped: boolean; finalMs: number }) {
  const [elapsed, setElapsed] = useState(stopped ? finalMs : Date.now() - startedAt);
  useEffect(() => {
    if (stopped) return;
    const id = setInterval(() => setElapsed(Date.now() - startedAt), 1000);
    return () => clearInterval(id);
  }, [startedAt, stopped]);
  return <span className="text-xs font-mono text-violet-400 tabular-nums">{fmt(stopped ? finalMs : elapsed)}</span>;
}
