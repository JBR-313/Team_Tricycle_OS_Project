# Presentation slides — course deliverable

The final slides and the talk are in **English**. Export the deck here as
`slides.pdf` so the graded slides live in the repo (not only in Canva).

**Narrative:** fixed kernel scheduling isn't optimal for every workload → use an
LLM as a *hint oracle* (the LLM proposes; the Algorithm Guard + xv6 decide whether
to follow; xv6 is the execution authority). Honest, measured finding: the LLM
**loses** in the quantitative decision hot path (algorithm choice, mid-run
switching, numeric burst prediction — classical methods win, shown with negative
controls) but **wins** at the human interface (natural-language intent → config,
trace explanation). Conclusion: *put the LLM at the OS's human-facing layer, not
its decision hot path.* See `docs/technical_report.md` for the full write-up.
