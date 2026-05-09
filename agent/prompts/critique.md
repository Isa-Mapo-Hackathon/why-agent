# Critique — Is the evidence strong enough to report?

**User question:** {user_question}

**Hypotheses and their supporting evidence:**
{hypotheses}

**Evidence chain ({evidence_count} tool calls):**
{evidence_summary}

**Retry count:** {retry_count} / {MAX_RETRIES}

---

## Your task

Evaluate whether the evidence collected is sufficient to answer the user's
question with reasonable confidence. Be pragmatic — the goal is a useful
answer, not a perfect one.

{question_type_checks}

### Advisory checks (bonus credit, not required)

These improve answer quality but are **not grounds for VERDICT: weak** on
their own:

- Overlap measurement between two compared groups
- Arithmetic decomposition of contribution percentages
- Segment-level confirmation in both time windows
- Composition vs behaviour decomposition for time-series

If the required checks pass and the evidence tells a coherent story, return
**VERDICT: strong** even if the advisory checks were not performed.

Only return **VERDICT: weak** if a required check clearly failed and one more
targeted tool call would materially change the conclusion.

---

## Response format

Start your response with exactly this line (no bold, no code fence, no extra
characters):

```
VERDICT: strong
```

or

```
VERDICT: weak
```

Then write 1–2 sentences justifying your decision. If weak, state specifically
what single gap to close — the retry will be directed at exactly that.
