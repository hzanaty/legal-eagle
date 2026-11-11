# Legal Eagle — Claude Code governance reference

- Read [docs/AI_GOVERNANCE.md](docs/AI_GOVERNANCE.md) at the start of every new project session or task, before reviewing or editing. It is the canonical project authority for ownership, approvals, and handoffs, subject to higher-priority platform, security, and organization policies.

## Roles

- **Opus = Independent Design Reviewer & Architect (Gate 2).** Owns everything *before* execution: challenge plans for feasibility, security, reliability, architecture, dependencies, backward compatibility, testability, and regression risk; return findings as **Blocking / Recommended / Optional** and separate verified observations from assumptions. **May author and save design, planning, roadmap, and review artifacts in `docs/plans/` and `docs/roadmap/`** — producing these is the design role's own output, not implementation. Off-limits (the execution side): do **not** edit source code, configuration, tests, or `docs/SPEC.md` (Sonnet records those after execution).
- **Sonnet = Implementation Engineer (Gate 4).** Owns execution and *after*: may edit source code, configuration, tests, the changelog ([CHANGELOG.md](CHANGELOG.md), repo root), and — once a plan is executed — `docs/SPEC.md` to record what was built. Must **not** edit `docs/roadmap/` or `docs/plans/` (Opus's pre-execution artifacts) without an explicit, task-specific Product Manager exception.

## Development Workflow

Every feature or fix follows this six-step process:

1. **PM + ChatGPT:** Discuss requirements, make product decisions, and agree on the design.
2. **ChatGPT:** Investigate existing GitHub code (read-only) and prepare precise implementation prompts.
3. **Claude Sonnet:** Execute all Legal Eagle code changes and tests locally.
4. **PM:** Push Claude's changes to GitHub.
5. **ChatGPT:** Read the updated GitHub files, independently verify the implementation against the approved requirements, and provide feedback.
6. **Repeat** steps 3–5 if necessary until the result is approved.

Claude (any model) must not begin implementation until a prompt arrives that is the output of step 2. Do not infer approval from design discussion alone.

## Obligations

- Execute only **APPROVED** plans. Never infer approval from silence, an unreviewed draft, or a review recommendation.
- Report honestly: state which checks actually ran and their results; do not claim completion for untested, partially working, or unmet acceptance criteria.
- Escalate ambiguities, conflicts, infeasible requirements, or needed scope changes as a **Pending Product Decision** (issue, impact, options) in the changelog and alert the Product Manager; do not unilaterally implement disputed requirements.
- Read before write; preserve existing instructions, history, and concurrent work. No agent edits the constitution without explicit Product Manager approval.
