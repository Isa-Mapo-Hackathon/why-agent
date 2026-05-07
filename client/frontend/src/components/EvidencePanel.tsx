"use client";

import { useState } from "react";
import type { EvidenceItem } from "@/lib/types";

function ToolBadge({ name }: { name: string }) {
  const map: Record<string, string> = {
    run_sql:          "bg-blue-900/60  text-blue-200  border-blue-700/60",
    inspect_schema:   "bg-violet-900/60 text-violet-200 border-violet-600/60",
    compare_periods:  "bg-emerald-900/60 text-emerald-200 border-emerald-700/60",
    decompose_metric: "bg-orange-900/60 text-orange-200 border-orange-700/60",
  };
  return (
    <span className={`px-2 py-0.5 rounded border text-xs font-mono ${map[name] ?? "bg-surface text-violet-200 border-frame"}`}>
      {name}
    </span>
  );
}

function DurationBadge({ ms }: { ms: number | null }) {
  if (ms === null) return null;
  return <span className="text-xs font-mono text-violet-600 tabular-nums">{ms < 1000 ? `${Math.round(ms)}ms` : `${(ms / 1000).toFixed(1)}s`}</span>;
}

function ArgValue({ label, value }: { label: string; value: unknown }) {
  if (typeof value === "string") {
    const isLong = value.length > 60 || value.includes("\n");
    return (
      <div>
        <span className="text-violet-500 text-xs">{label}: </span>
        {isLong
          ? <pre className="mt-1 text-xs bg-black/40 rounded p-2 text-violet-200 whitespace-pre-wrap break-words font-mono">{value}</pre>
          : <span className="text-xs text-white font-mono">{value}</span>
        }
      </div>
    );
  }
  if (value === null || value === undefined) return null;
  return (
    <div>
      <span className="text-violet-500 text-xs">{label}: </span>
      <span className="text-xs text-white font-mono">{JSON.stringify(value)}</span>
    </div>
  );
}

function OutputPreview({ toolName, output }: { toolName: string; output: Record<string, unknown> }) {
  if (output.error) return null;

  if (toolName === "run_sql") {
    const rows = output.rows as Record<string, unknown>[] | undefined;
    const count = (output.row_count as number) ?? rows?.length ?? 0;
    if (!rows || rows.length === 0) return <p className="text-xs text-violet-400">{count} rows returned</p>;
    const cols = Object.keys(rows[0]);
    return (
      <div>
        <p className="text-xs text-violet-500 mb-1">{count} row{count !== 1 ? "s" : ""}{(output.truncated as boolean) ? " (truncated)" : ""}</p>
        <div className="overflow-x-auto">
          <table className="text-xs w-full">
            <thead><tr>{cols.map(c => <th key={c} className="text-left text-violet-500 pr-4 pb-1 font-normal">{c}</th>)}</tr></thead>
            <tbody>{rows.slice(0, 3).map((row, i) => (
              <tr key={i}>{cols.map(c => <td key={c} className="text-white pr-4 py-0.5 font-mono">{String(row[c] ?? "")}</td>)}</tr>
            ))}</tbody>
          </table>
          {count > 3 && <p className="text-xs text-violet-600 mt-1">+{count - 3} more rows</p>}
        </div>
      </div>
    );
  }

  if (toolName === "compare_periods") {
    const { before_value, after_value, abs_delta, pct_delta } = output as Record<string, number | null>;
    if (before_value === undefined) return null;
    const trend = (abs_delta ?? 0) >= 0 ? "text-emerald-400" : "text-red-400";
    return (
      <div className="flex items-center gap-3 text-sm">
        <span className="text-violet-300">{before_value?.toFixed(4)}</span>
        <span className="text-violet-600">→</span>
        <span className="text-white font-semibold">{after_value?.toFixed(4)}</span>
        <span className={`font-mono ${trend}`}>{(abs_delta ?? 0) > 0 ? "+" : ""}{abs_delta?.toFixed(4)}</span>
        <span className={`font-mono ${trend}`}>({pct_delta !== null ? `${pct_delta > 0 ? "+" : ""}${pct_delta?.toFixed(1)}%` : "n/a"})</span>
      </div>
    );
  }

  if (toolName === "decompose_metric") {
    const slices = output.slices as { slice_value: string; anomaly_score: number }[] | undefined;
    if (!slices || slices.length === 0) return null;
    return (
      <div className="space-y-1">
        {slices.slice(0, 3).map((s, i) => (
          <div key={i} className="flex items-center gap-2 text-sm">
            <span className="text-violet-600 w-4 font-mono">{i + 1}.</span>
            <span className="text-white font-mono">{s.slice_value}</span>
            <span className="text-violet-500 text-xs">anomaly:</span>
            <span className={`font-mono text-xs ${s.anomaly_score > 0 ? "text-orange-300" : "text-blue-300"}`}>
              {s.anomaly_score > 0 ? "+" : ""}{s.anomaly_score?.toFixed(2)}
            </span>
          </div>
        ))}
        {slices.length > 3 && <p className="text-xs text-violet-600">+{slices.length - 3} more</p>}
      </div>
    );
  }

  if (toolName === "inspect_schema") {
    const tables = output.tables as string[] | undefined;
    const cols = output.columns as unknown[] | undefined;
    if (tables) return <p className="text-sm text-violet-200">{tables.length} table{tables.length !== 1 ? "s" : ""}: {tables.join(", ")}</p>;
    if (cols) return <p className="text-sm text-violet-200">{cols.length} column{cols.length !== 1 ? "s" : ""} described</p>;
  }

  return null;
}

function EvidenceRow({ item, index, isLatest, streaming }: { item: EvidenceItem; index: number; isLatest: boolean; streaming: boolean }) {
  const hasError = Boolean(item.output?.error);
  const [open, setOpen] = useState(hasError || (isLatest && streaming));

  return (
    <div className={`border rounded-lg ${
      hasError ? "border-red-700 bg-red-950/20"
      : isLatest && streaming ? "border-violet-500 bg-violet-950/20"
      : "border-frame bg-surface"
    }`}>
      <button onClick={() => setOpen(o => !o)} className="w-full flex items-center gap-2 px-3 py-2.5 text-left">
        <span className="text-xs font-mono text-violet-600 w-5">{index + 1}</span>
        <ToolBadge name={item.tool_name} />
        <span className="text-xs font-mono text-violet-500">{item.phase}</span>
        <DurationBadge ms={item.duration_ms} />
        {isLatest && streaming
          ? <span className="ml-auto w-2 h-2 rounded-full bg-violet-400 animate-pulse" />
          : <span className="ml-auto text-sm">{hasError ? "⚠️" : "✅"}</span>}
        <span className="text-violet-600 text-xs">{open ? "▲" : "▼"}</span>
      </button>

      {open && (
        <div className="px-4 pb-4 space-y-3 border-t border-frame pt-3">
          {item.reasoning && (
            <div className="border-l-2 border-violet-500 bg-violet-950/30 rounded-r px-3 py-2">
              <p className="text-xs font-semibold text-violet-300 mb-1">Agent thought</p>
              <p className="text-sm text-violet-100 leading-relaxed">{item.reasoning}</p>
            </div>
          )}
          <div>
            <p className="text-xs font-mono text-violet-500 mb-1.5 uppercase tracking-wider">Input</p>
            <div className="bg-black/30 rounded-lg p-3 space-y-1.5">
              {Object.entries(item.args).map(([k, v]) => <ArgValue key={k} label={k} value={v} />)}
            </div>
          </div>
          {!hasError && (
            <div>
              <p className="text-xs font-mono text-violet-500 mb-1.5 uppercase tracking-wider">Result</p>
              <div className="bg-black/30 rounded-lg p-3">
                <OutputPreview toolName={item.tool_name} output={item.output} />
              </div>
            </div>
          )}
          {hasError && (
            <div className="bg-red-950/30 rounded-lg p-3">
              <p className="text-sm text-red-400 font-medium">Error: {item.output.error}</p>
              {item.output.hint && <p className="text-xs text-violet-400 mt-1">Hint: {item.output.hint}</p>}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

export default function EvidencePanel({ evidence, streaming = false }: { evidence: EvidenceItem[]; streaming?: boolean }) {
  const [expanded, setExpanded] = useState(false);
  if (evidence.length === 0) return null;

  if (streaming) {
    return (
      <div className="space-y-2">
        {evidence.map((e, i) => <EvidenceRow key={i} item={e} index={i} isLatest={i === evidence.length - 1} streaming />)}
      </div>
    );
  }

  return (
    <div>
      <button onClick={() => setExpanded(e => !e)}
        className="flex items-center gap-2 text-sm text-violet-400 hover:text-violet-200 transition-colors mb-2">
        <span>🔍</span>
        <span>{evidence.length} tool calls</span>
        <span className="text-violet-600 text-xs">{expanded ? "▲" : "▼"}</span>
      </button>
      {expanded && (
        <div className="space-y-2">
          {evidence.map((e, i) => <EvidenceRow key={i} item={e} index={i} isLatest={false} streaming={false} />)}
        </div>
      )}
    </div>
  );
}
