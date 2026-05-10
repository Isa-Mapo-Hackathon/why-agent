"use client";

import { useState } from "react";

const QUESTIONS = [
  "Why did campaign 230 underperform campaign 150?",
  "Why did many email conversions happen within a minute of send?",
  "Recipients who got more messages converted better or worse than those who got less messages? Does sending more emails drive higher conversions?"
];

interface Props { onSelect: (q: string) => void; disabled: boolean; }

export default function DemoQuestions({ onSelect, disabled }: Props) {
  const [open, setOpen] = useState(true);

  return (
    <div className="space-y-2">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        aria-expanded={open}
        className="w-full flex items-start gap-2 rounded-lg px-2 py-2 text-left text-violet-400 hover:bg-elevated hover:text-violet-200 transition-colors"
      >
        <span className="text-[10px] font-mono text-violet-600 w-3 pt-0.5">{open ? "▼" : "▶"}</span>
        <span className="min-w-0">
          <span className="block text-xs font-mono uppercase tracking-widest">Start Here</span>
          <span className="mt-0.5 block text-[10px] font-mono normal-case tracking-normal text-violet-600">
            Demo questions you may be interested in
          </span>
        </span>
        <span className="ml-auto text-[10px] font-mono text-violet-600 pt-0.5">{QUESTIONS.length}</span>
      </button>

      {open && (
        <div className="ml-3 pl-3 border-l border-frame space-y-1">
          {QUESTIONS.map((q, i) => (
            <button key={q} onClick={() => onSelect(q)} disabled={disabled}
              className="w-full text-left group flex items-start gap-2 px-2 py-1.5 rounded-lg hover:bg-elevated transition-colors disabled:opacity-30 disabled:cursor-not-allowed">
              <span className="text-[10px] font-mono text-violet-500 mt-0.5 shrink-0 group-hover:text-violet-300 transition-colors">
                #{String(i + 1).padStart(2, "0")}
              </span>
              <span className="text-xs text-violet-200 group-hover:text-white transition-colors leading-snug">{q}</span>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
