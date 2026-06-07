# Presentation Slides — deliverable #4 (§5)

The final Week-14 presentation **slides and the spoken presentation must be in
English** (§6).

## Files
- `slides.pdf` — **[TEAM TODO]** export the final English deck here
  (Canva → Download → PDF) so the graded slides live in the repo, not only in Canva.
- Source: Canva (team's private edit link — not committed; export the PDF instead).

## Narrative (aligned with technical_report.md)
1. **Premise (confirmed):** fixed kernel scheduling is not optimal for all workloads.
2. **Design:** LLM as a *hint oracle* for xv6 scheduling — LLM proposes, Algorithm
   Guard + xv6 decide whether to follow; xv6 is the execution authority.
3. **What the system delivers:** a closed loop that beats a fixed stock-RR default,
   with a safety net that guarantees the LLM can never degrade execution, plus
   natural-language trace explanation.
4. **Honest evaluation (limitations):** the LLM's standalone algorithm *selection* is
   information-bounded; the measured wins are burst-ordering prediction + safe
   integration + observability. We characterised *where the LLM helps and where it
   does not* by measurement.

See `docs/presentation_defense_notes.md` for anticipated Q&A.
