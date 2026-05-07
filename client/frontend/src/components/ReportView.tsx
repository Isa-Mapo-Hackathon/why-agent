"use client";

import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import type { ReportData } from "@/lib/types";

function stripThinkTags(text: string): string {
  return text.replace(/<think>[\s\S]*?<\/think>/g, "").trim();
}

export default function ReportView({ report }: { report: ReportData }) {
  const text = stripThinkTags(report.text ?? "");
  const hypotheses = report.hypotheses ?? [];

  return (
    <div className="space-y-4">
      <div className="report-body">
        <ReactMarkdown remarkPlugins={[remarkGfm]} components={{
          table: ({ children }) => (
            <div className="overflow-x-auto my-4">
              <table className="min-w-full text-sm border border-frame rounded-lg overflow-hidden">{children}</table>
            </div>
          ),
          thead: ({ children }) => <thead className="bg-surface text-violet-200">{children}</thead>,
          tbody: ({ children }) => <tbody className="divide-y divide-frame">{children}</tbody>,
          tr:   ({ children }) => <tr className="hover:bg-surface/50">{children}</tr>,
          th:   ({ children }) => <th className="px-3 py-2 text-left font-semibold text-violet-300 whitespace-nowrap">{children}</th>,
          td:   ({ children }) => <td className="px-3 py-2 text-violet-100">{children}</td>,
          h1:   ({ children }) => <h1 className="text-2xl font-bold text-white mt-6 mb-3 border-b border-frame pb-2">{children}</h1>,
          h2:   ({ children }) => <h2 className="text-xl font-semibold text-white mt-5 mb-2">{children}</h2>,
          h3:   ({ children }) => <h3 className="text-base font-semibold text-violet-300 mt-4 mb-1.5">{children}</h3>,
          p:    ({ children }) => <p className="text-violet-100 mb-3 leading-7 text-sm">{children}</p>,
          ul:   ({ children }) => <ul className="list-disc list-outside pl-5 text-violet-100 mb-3 space-y-1">{children}</ul>,
          ol:   ({ children }) => <ol className="list-decimal list-outside pl-5 text-violet-100 mb-3 space-y-1">{children}</ol>,
          li:   ({ children }) => <li className="text-violet-100 text-sm leading-relaxed">{children}</li>,
          strong: ({ children }) => <strong className="text-white font-semibold">{children}</strong>,
          hr:   () => <hr className="border-frame my-5" />,
          code: ({ children }) => <code className="text-violet-300 font-mono text-xs bg-violet-950/50 px-1.5 py-0.5 rounded">{children}</code>,
          blockquote: ({ children }) => <blockquote className="border-l-2 border-violet-500 pl-4 text-violet-300 italic my-3">{children}</blockquote>,
        }}>
          {text}
        </ReactMarkdown>
      </div>

      {hypotheses.length > 0 && (
        <details className="border border-frame rounded-lg">
          <summary className="px-4 py-2.5 text-sm text-violet-400 cursor-pointer hover:text-violet-200 transition-colors">
            Hypotheses ({hypotheses.length})
          </summary>
          <div className="px-4 pb-3 space-y-2">
            {hypotheses.map((h) => (
              <div key={h.id} className="text-sm">
                <span className="font-semibold text-violet-300">{h.status === "confirmed" ? "✅" : "🔍"} [{h.id}]</span>
                {" "}<span className="text-violet-100">{h.description}</span>
              </div>
            ))}
          </div>
        </details>
      )}

      <p className="text-xs text-violet-600 font-mono">
        {report.evidence_count} tool calls · {hypotheses.length} hypotheses
        {report.error && <span className="text-red-400 ml-2">⚠ {report.error}</span>}
      </p>
    </div>
  );
}
