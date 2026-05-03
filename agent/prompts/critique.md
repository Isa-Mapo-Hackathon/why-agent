# Critique — Is the evidence strong enough to report?

**User question:** {user_question}

**Hypotheses and their supporting evidence:**
{hypotheses}

**Evidence chain ({evidence_count} tool calls):**
{evidence_summary}

**Retry count:** {retry_count} / {MAX_RETRIES}

---

## Your task

Evaluate whether the evidence collected so far is sufficient to answer
the user's question with confidence. Consider:

1. **Causal signal** — Does the top-ranked anomalous slice actually explain the metric movement?
2. **Confounds** — Could another dimension or time window account for the same delta?
3. **Cross-check passed** — Did any cross-check queries contradict the leading hypothesis?
4. **Alternative ruled out** — Did you explicitly investigate and dismiss other plausible causes?

## Response format

Start your response with exactly one of these prefixes on its own line:

```
VERDICT: strong
```

or

```
VERDICT: weak
```

Then write 1–2 sentences justifying your decision.

**VERDICT: strong**
> A brief (1–2 sentence) justification of why the leading hypothesis is well-supported.

**VERDICT: weak**
> A brief (1–2 sentence) explanation of what is missing and what you would investigate next.
> The graph will loop back to the `decompose` phase.