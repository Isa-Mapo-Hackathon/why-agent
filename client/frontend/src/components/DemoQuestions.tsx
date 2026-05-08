"use client";

import { useState } from "react";

const QUESTIONS = [
  "Why did campaign 230 underperform campaign 150?",
  "Why did message open rate drop in the most recent campaign?",
  "Why does campaign 361 convert 60x better than campaign 296?",
  "Why is weekend engagement consistently lower than weekday?",
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
        className="w-full flex items-center gap-2 rounded-lg px-2 py-2 text-left text-violet-400 hover:bg-elevated hover:text-violet-200 transition-colors"
      >
        <span className="text-[10px] font-mono text-violet-600 w-3">{open ? "▼" : "▶"}</span>
        <span className="text-xs font-mono uppercase tracking-widest">Demo Questions</span>
        <span className="ml-auto text-[10px] font-mono text-violet-600">{QUESTIONS.length}</span>
      </button>

      {open && (
        <div className="ml-3 pl-3 border-l border-frame space-y-1">
          {QUESTIONS.map((q, i) => (
            <button key={q} onClick={() => onSelect(q)} disabled={disabled}
              className="w-full text-left group flex items-start gap-2.5 px-2 py-2.5 rounded-lg hover:bg-elevated transition-colors disabled:opacity-30 disabled:cursor-not-allowed">
              <span className="text-xs font-mono text-violet-500 mt-0.5 shrink-0 group-hover:text-violet-300 transition-colors">
                #{String(i + 1).padStart(2, "0")}
              </span>
              <span className="text-sm text-violet-200 group-hover:text-white transition-colors leading-relaxed">{q}</span>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
