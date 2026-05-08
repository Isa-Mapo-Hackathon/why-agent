"use client";

import { useEffect, useRef, useState } from "react";
import type { ChatEntry, EvidenceItem, Phase, ReportData } from "@/lib/types";
import { runInvestigation } from "@/lib/sseClient";
import ChatInput from "@/components/ChatInput";
import DemoQuestions from "@/components/DemoQuestions";
import ElapsedTimer from "@/components/ElapsedTimer";
import EvidencePanel from "@/components/EvidencePanel";
import PhaseTimeline from "@/components/PhaseTimeline";
import ReportView from "@/components/ReportView";

function newEntry(question: string): ChatEntry {
  return { question, phases: [], evidence: [], hypotheses: [], report: null, error: null, streaming: true, startedAt: Date.now(), elapsedMs: 0 };
}

function ThinkingDots() {
  return (
    <span className="inline-flex items-center gap-1">
      {[0, 1, 2].map((i) => (
        <span key={i} className="w-1.5 h-1.5 rounded-full bg-violet-400 animate-bounce"
          style={{ animationDelay: `${i * 0.15}s`, animationDuration: "0.8s" }} />
      ))}
    </span>
  );
}

export default function Home() {
  const [history, setHistory] = useState<ChatEntry[]>([]);
  const [streaming, setStreaming] = useState(false);
  const abortRef = useRef<AbortController | null>(null);
  const scrollRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    scrollRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [history]);

  const submit = async (question: string) => {
    if (streaming) return;
    setHistory((h) => [...h, newEntry(question)]);
    setStreaming(true);
    abortRef.current = new AbortController();
    try {
      await runInvestigation(question, (evt) => {
        setHistory((h) => {
          const cur = h[h.length - 1];
          if (!cur) return h;
          const u = { ...cur };
          if (evt.type === "phase") u.phases = [...new Set([...u.phases, evt.phase as Phase])];
          else if (evt.type === "evidence") { const { type: _, ...item } = evt; u.evidence = [...u.evidence, item as EvidenceItem]; }
          else if (evt.type === "report") {
            const { type: _, ...r } = evt;
            u.phases = [...new Set([...u.phases, "critique", "report"])] as Phase[];
            u.report = r as ReportData;
            u.streaming = false;
            u.elapsedMs = Date.now() - cur.startedAt;
          }
          else if (evt.type === "error") { u.error = evt.message; u.streaming = false; u.elapsedMs = Date.now() - cur.startedAt; }
          else if (evt.type === "done") { u.streaming = false; u.elapsedMs = Date.now() - cur.startedAt; }
          return [...h.slice(0, -1), u];
        });
      }, abortRef.current.signal);
    } catch (err) {
      if ((err as Error).name !== "AbortError") {
        setHistory((h) => {
          const cur = h[h.length - 1];
          if (!cur) return h;
          return [
            ...h.slice(0, -1),
            { ...cur, error: String(err), streaming: false, elapsedMs: Date.now() - cur.startedAt },
          ];
        });
      }
    } finally { setStreaming(false); }
  };

  return (
    <div className="flex overflow-hidden bg-bg" style={{ height: "100svh" }}>

      {/* Sidebar */}
      <aside className="w-56 shrink-0 flex flex-col bg-bg border-r border-frame">
        <div className="px-5 py-5 border-b border-frame">
          <div className="flex items-center gap-2.5">
            <div className="w-2 h-2 rounded-full bg-violet-400 animate-glow shrink-0" />
            <span className="font-display font-bold text-base text-white">why-agent</span>
          </div>
          <p className="text-xs text-violet-400 mt-1 pl-[18px]">root-cause intelligence</p>
        </div>
        <div className="flex-1 overflow-y-auto p-3">
          <DemoQuestions onSelect={submit} disabled={streaming} />
        </div>
        <div className="px-5 py-3 border-t border-frame flex items-center gap-2">
          <div className={`w-2 h-2 rounded-full transition-colors ${streaming ? "bg-violet-400 animate-pulse" : "bg-frame"}`} />
          <span className="text-xs font-mono text-violet-400">{streaming ? "investigating" : "ready"}</span>
        </div>
      </aside>

      {/* Main */}
      <main className="flex-1 flex flex-col min-w-0 bg-bg">
        <div className="flex-1 overflow-y-auto px-6 py-8 space-y-8">

          {history.length === 0 && (
            <div className="flex flex-col items-center justify-center h-full gap-4">
              <div className="w-12 h-12 rounded-2xl border border-frame bg-surface flex items-center justify-center">
                <span className="text-violet-400 text-xl">?</span>
              </div>
              <p className="text-violet-400 text-sm">Select a case file or ask a question</p>
            </div>
          )}

          {history.map((entry, i) => (
            <div key={`${entry.startedAt}-${i}`} className="space-y-4">

              {/* User message */}
              <div className="flex justify-end">
                <div className="max-w-2xl">
                  <p className="text-xs text-violet-400 text-right mb-1.5 font-mono uppercase tracking-wider">Query</p>
                  <div className="bg-surface border border-frame text-white px-4 py-3 rounded-2xl rounded-tr-sm text-sm leading-relaxed">
                    {entry.question}
                  </div>
                </div>
              </div>

              {/* Agent card */}
              <div className="max-w-4xl border border-frame rounded-2xl rounded-tl-sm overflow-hidden">
                <div className="flex items-center justify-between px-4 py-3 bg-surface border-b border-frame">
                  <div className="flex items-center gap-2.5">
                    {entry.streaming ? (
                      <><ThinkingDots /><span className="text-xs font-mono text-violet-300 uppercase tracking-widest ml-1">Investigating</span></>
                    ) : (
                      <><div className="w-2 h-2 rounded-full bg-violet-500" /><span className="text-xs font-mono text-violet-300 uppercase tracking-widest">Complete</span></>
                    )}
                  </div>
                  <ElapsedTimer startedAt={entry.startedAt} stopped={!entry.streaming} finalMs={entry.elapsedMs} />
                </div>
                <div className="bg-bg p-5 space-y-5">
                  {entry.phases.length > 0 && (
                    <PhaseTimeline currentPhase={entry.streaming ? entry.phases[entry.phases.length - 1] : null} completedPhases={entry.phases} />
                  )}
                  {entry.report && <ReportView report={entry.report} />}
                  {entry.error && (
                    <div className="border border-red-800 bg-red-950/30 rounded-lg px-3 py-2">
                      <p className="text-sm text-red-400">⚠ {entry.error}</p>
                    </div>
                  )}
                  <EvidencePanel evidence={entry.evidence} streaming={entry.streaming} />
                </div>
              </div>

            </div>
          ))}
          <div ref={scrollRef} />
        </div>

        <div className="border-t border-frame bg-bg px-6 py-4">
          <ChatInput onSubmit={submit} disabled={streaming} />
        </div>
      </main>
    </div>
  );
}
