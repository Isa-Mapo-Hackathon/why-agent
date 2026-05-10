"use client";

import { useState } from "react";

const PANEL_ID = "how-it-works-panel";

export default function HowItWorks() {
  const [open, setOpen] = useState(false);

  return (
    <div className="space-y-2">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        aria-expanded={open}
        aria-controls={PANEL_ID}
        aria-label="Toggle how it works panel"
        className="w-full flex items-center gap-2 rounded-lg px-2 py-2 text-left text-violet-400 hover:bg-elevated hover:text-violet-200 transition-colors"
      >
        <span className="text-[10px] font-mono text-violet-600 w-3">
          {open ? "▼" : "▶"}
        </span>
        <span className="text-xs font-mono uppercase tracking-widest">
          How It Works
        </span>
      </button>

      {open && (
        <div id={PANEL_ID} className="ml-3 pl-3 border-l border-frame pb-1">
          <p className="px-2 py-1.5 text-xs text-violet-200 leading-snug">
            <span className="text-[13px] font-semibold text-violet-100">
              why-agent
            </span>{" "}
            runs a multi-phase investigation - It forms hypotheses, queries your
            data, tests alternatives, and self-critiques before reporting. Most
            investigations take 3-10 minutes.
          </p>
        </div>
      )}
    </div>
  );
}
