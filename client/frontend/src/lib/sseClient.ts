import type { SseEvent } from "./types";

export async function runInvestigation(
  question: string,
  onEvent: (event: SseEvent) => void,
  signal?: AbortSignal,
): Promise<void> {
  const response = await fetch("/api/investigate", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ question }),
    signal,
  });

  if (!response.ok) {
    throw new Error(`Server error: ${response.status}`);
  }

  const reader = response.body?.getReader();
  if (!reader) throw new Error("No response body");

  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split("\n");
    buffer = lines.pop() ?? "";

    let eventType = "";
    for (const line of lines) {
      if (line.startsWith("event:")) {
        eventType = line.slice(6).trim();
      } else if (line.startsWith("data:")) {
        const raw = line.slice(5).trim();
        try {
          const parsed = JSON.parse(raw) as SseEvent;
          onEvent(parsed);
          if (parsed.type === "done") return;
        } catch {
          // malformed line — skip
        }
      }
    }
    void eventType; // consumed above via parsed.type
  }

  // Body stream closed quietly while signal was already aborted — surface it so
  // the caller can distinguish a user-cancel from a clean server-side finish.
  if (signal?.aborted) {
    throw new DOMException("Aborted", "AbortError");
  }
}
