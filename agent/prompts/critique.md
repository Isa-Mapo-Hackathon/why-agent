# Critique — Is the evidence strong enough to report?

**User question:** {user_question}

**Hypotheses and their supporting evidence:**
{hypotheses}

**Evidence chain ({evidence_count} tool calls):**
{evidence_summary}

**Retry count:** {retry_count} / {MAX_RETRIES}

---

## Your task

Evaluate whether the evidence collected so far is sufficient to answer the
user's question with confidence. Apply different checks depending on the
shape of the question.

### Universal checks (apply to every investigation)

1. **Headline numbers exist for every entity or period in the question.**
   If the question compares A and B, both A and B must have been measured.
   If the question asks how a metric changed, both before and after windows
   must have been measured.

2. **Alternative explanations were tested, not assumed away.** At least one
   plausible alternative cause must have been investigated and either
   confirmed or dismissed with explicit evidence.

3. **The leading hypothesis was confirmed with direct data, not inferred
   from aggregates.** If the agent's conclusion involves a specific entity,
   that entity's actual attributes should appear in the evidence.

### Cross-sectional question checks (when the question compares two entities or groups)

4. **The "measure on overlap" move was performed** — when both entities have
   shared sub-observations (recipients, days, products), the agent should
   have re-measured the metric on the overlap subset and observed how the
   gap changed. Without this, audience selection effects are not separated
   from genuine entity-quality effects.

5. **Contribution was decomposed with explicit numbers and percentages.**
   The agent should have stated arithmetically what fraction of the
   headline gap is attributable to each factor — for example,
   *"aggregate gap = 19pp, overlap gap = 2pp, selection effect ≈ 17pp ≈
   90% of total, genuine effect ≈ 2pp ≈ 10% of total."* A qualitative
   claim like *"mostly audience"* without numbers does **not** satisfy
   this check.

### Time-series question checks (when the question compares two time windows)

6. **Composition was checked.** The agent should have examined whether
   segment weights shifted between the windows, not just whether segment
   rates moved. A rate-stable / weight-shifted pattern is composition-driven.

7. **The driver segment was confirmed in both windows.** If a segment is
   identified as the cause of a change, the agent should have measured that
   segment's metric in both periods, not only in the after window.

8. **Contribution was decomposed with explicit numbers and percentages.**
   The agent should have stated arithmetically how much of the aggregate
   change is behavior (segment rates moving) vs composition (segment
   weights shifting) — for example, *"aggregate change = −5pp, behavior
   component ≈ −1pp ≈ 20%, composition component ≈ −4pp ≈ 80%."* A
   qualitative claim without numbers does **not** satisfy this check.

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

Then write 1–3 sentences justifying your decision.

- **VERDICT: strong** — the leading hypothesis is well-supported by
  quantitative evidence, alternatives have been ruled out with data, and
  the question-shape-specific checks above were performed. Show your
  reasoning by referencing specific tool calls or numbers.

- **VERDICT: weak** — at least one required check was skipped or its
  evidence is insufficient. State **specifically** what is missing — the
  retry pass will be directed to close that exact gap. Examples:
  *"The measure-on-overlap step was not performed for the campaign A vs
  campaign B comparison."*
  *"Audience composition was not compared between the two segments."*
  *"The driver segment's metric was only measured in the after window, not
  the before window."*

The graph will loop back to the `decompose` phase if you return WEAK, and
will inject your justification as a targeted directive.
