"use client";

import type { Phase } from "@/lib/types";

const PHASES: Phase[] = ["plan", "decompose", "drill", "cross_check", "critique", "report"];
const LABELS: Record<Phase, string> = {
  plan: "Plan", decompose: "Decompose", drill: "Drill",
  cross_check: "X-Check", critique: "Critique", report: "Report",
};

interface Props { currentPhase: Phase | null; completedPhases: Phase[]; }

export default function PhaseTimeline({ currentPhase, completedPhases }: Props) {
  return (
    <div className="flex items-center py-2">
      {PHASES.map((phase, i) => {
        const isDone   = completedPhases.includes(phase) && phase !== currentPhase;
        const isActive = phase === currentPhase;
        return (
          <div key={phase} className="flex items-center">
            <div className="flex flex-col items-center gap-1.5">
              <div className={`w-3 h-3 rounded-full transition-all duration-500 ${
                isActive ? "bg-violet-400 animate-glow scale-110"
                : isDone  ? "bg-violet-400"
                :           "bg-frame"
              }`} />
              <span className={`text-[10px] font-mono whitespace-nowrap transition-colors ${
                isActive ? "text-violet-300 font-semibold"
                : isDone  ? "text-violet-400"
                :           "text-violet-700"
              }`}>{LABELS[phase]}</span>
            </div>
            {i < PHASES.length - 1 && (
              <div className={`w-8 h-px mx-1 mb-4 ${isDone ? "bg-violet-500" : "bg-frame"}`} />
            )}
          </div>
        );
      })}
    </div>
  );
}
