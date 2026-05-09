"use client";

import type { Phase } from "@/lib/types";

const PHASES: Phase[] = ["plan", "decompose", "drill", "cross_check", "critique", "report"];
const LABELS: Record<Phase, string> = {
  plan: "Plan", decompose: "Decompose", drill: "Drill",
  cross_check: "X-Check", critique: "Critique", report: "Report",
};
const DESCRIPTIONS: Record<Phase, string> = {
  plan: "Frame the question and choose the first checks.",
  decompose: "Break the metric into likely drivers and segments.",
  drill: "Investigate the strongest candidate causes in detail.",
  cross_check: "Verify the explanation against alternate slices.",
  critique: "Check whether the evidence is strong enough.",
  report: "Summarize the answer, evidence, and next steps.",
};

interface Props { currentPhase: Phase | null; completedPhases: Phase[]; }

export default function PhaseTimeline({ currentPhase, completedPhases }: Props) {
  return (
    <div className={`flex w-full items-start pt-2 ${currentPhase ? "pb-10" : "pb-2"}`}>
      {PHASES.map((phase, i) => {
        const isDone   = completedPhases.includes(phase) && phase !== currentPhase;
        const isActive = phase === currentPhase;
        const tooltipAlign =
          i === 0
            ? "left-0"
            : i === PHASES.length - 1
              ? "right-0"
              : "left-1/2 -translate-x-1/2";
        return (
          <div key={phase} className="flex flex-1 items-start last:flex-none">
            <div className="relative flex flex-col items-center gap-1.5">
              <div className={`w-3 h-3 rounded-full transition-all duration-500 ${
                isActive ? "bg-violet-400 animate-glow scale-110"
                : isDone  ? "bg-violet-400"
                :           "bg-frame"
              }`} />
              <span className={`flex items-center gap-1 text-[10px] font-mono whitespace-nowrap transition-colors ${
                isActive ? "text-violet-300 font-semibold"
                : isDone  ? "text-violet-400"
                :           "text-violet-700"
              }`}>
                {LABELS[phase]}
                {currentPhase && (
                  <span className="relative group/info inline-flex">
                    <svg
                      aria-hidden="true"
                      viewBox="0 0 24 24"
                      fill="none"
                      stroke="currentColor"
                      strokeWidth="2"
                      className="w-3 h-3 text-violet-600 group-hover/info:text-violet-300"
                    >
                      <path strokeLinecap="round" strokeLinejoin="round" d="M12 17v-5" />
                      <path strokeLinecap="round" strokeLinejoin="round" d="M12 8h.01" />
                      <path strokeLinecap="round" strokeLinejoin="round" d="M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0Z" />
                    </svg>
                    <span className={`pointer-events-none absolute top-full z-20 mt-1.5 hidden w-52 max-w-[min(13rem,calc(100vw-3rem))] whitespace-normal break-words rounded-md border border-frame bg-surface px-2.5 py-1.5 text-left text-[10px] font-mono leading-snug text-violet-200 shadow-xl group-hover/info:block ${tooltipAlign}`}>
                      {DESCRIPTIONS[phase]}
                    </span>
                  </span>
                )}
              </span>
            </div>
            {i < PHASES.length - 1 && (
              <div className={`mx-4 mt-1.5 h-px flex-1 ${isDone ? "bg-violet-500" : "bg-frame"}`} />
            )}
          </div>
        );
      })}
    </div>
  );
}
