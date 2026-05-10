"use client";

import { useState } from "react";

interface Props {
  onSubmit: (question: string) => void;
  onAbort?: () => void;
  disabled: boolean;
}

export default function ChatInput({ onSubmit, onAbort, disabled }: Props) {
  const [value, setValue] = useState("");
  const submit = () => {
    const q = value.trim();
    if (!q || disabled) return;
    onSubmit(q);
    setValue("");
  };

  return (
    <div
      className={`flex items-center rounded-xl overflow-hidden border transition-colors ${
        disabled
          ? "border-frame"
          : "border-frame focus-within:border-violet-500"
      } bg-surface`}
    >
      <span className="pl-4 pr-2 font-mono text-violet-400 text-sm select-none">
        ❯
      </span>
      <textarea
        value={value}
        onChange={(e) => setValue(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Enter" && !e.shiftKey) {
            e.preventDefault();
            submit();
          }
        }}
        placeholder="Why did campaign A outperform B?"
        disabled={disabled}
        rows={1}
        className="flex-1 bg-transparent py-3.5 text-sm text-white placeholder-violet-700 resize-none focus:outline-none font-mono"
      />
      {disabled && onAbort ? (
        <button
          type="button"
          onClick={onAbort}
          aria-label="Stop investigation"
          className="px-5 py-3.5 bg-violet-600 hover:bg-violet-500 text-white text-xs font-mono uppercase tracking-widest transition-colors shrink-0 self-stretch flex items-center"
        >
          Stop ■
        </button>
      ) : (
        <button
          type="button"
          onClick={submit}
          disabled={disabled || !value.trim()}
          aria-label="Run investigation"
          className="px-5 py-3.5 bg-violet-600 hover:bg-violet-500 disabled:bg-frame disabled:text-violet-700 text-white text-xs font-mono uppercase tracking-widest transition-colors shrink-0 self-stretch flex items-center"
        >
          Run →
        </button>
      )}
    </div>
  );
}
