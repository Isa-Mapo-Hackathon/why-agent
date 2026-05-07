export type Phase =
  | "plan"
  | "decompose"
  | "drill"
  | "cross_check"
  | "critique"
  | "report";

export interface EvidenceItem {
  index: number;
  phase: Phase;
  tool_name: string;
  args: Record<string, unknown>;
  output: Record<string, unknown> & { error?: string; hint?: string };
  reasoning: string | null;
  timestamp: string;
  duration_ms: number | null;
}

export interface HypothesisItem {
  id: string;
  description: string;
  status: string;
  supporting_evidence: string[];
  weakening_evidence: string[];
}

export interface ReportData {
  user_question: string;
  text: string;
  hypotheses: HypothesisItem[];
  evidence_count: number;
  critique_passed: boolean;
  error: string | null;
}

export type SseEvent =
  | { type: "run_started"; run_id: string; user_question: string }
  | { type: "phase"; phase: Phase; retry_count: number }
  | ({ type: "evidence" } & EvidenceItem)
  | { type: "hypothesis_update"; hypotheses: HypothesisItem[] }
  | {
      type: "critique";
      passed: boolean;
      feedback: string | null;
      retry_count: number;
    }
  | ({ type: "report" } & ReportData)
  | { type: "error"; message: string }
  | { type: "done" };

export interface ChatEntry {
  question: string;
  phases: Phase[];
  evidence: EvidenceItem[];
  hypotheses: HypothesisItem[];
  report: ReportData | null;
  error: string | null;
  streaming: boolean;
  startedAt: number;
  elapsedMs: number;
}
