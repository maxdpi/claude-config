# conventions/

Universal conventions for agents and skills.

## Files

| File                | What                                     | When to read                                            |
| ------------------- | ---------------------------------------- | ------------------------------------------------------- |
| `documentation.md`  | CLAUDE.md/README.md format specification | Writing CLAUDE.md, creating README.md, doc-sync skill   |
| `intent-markers.md` | :PERF:/:UNSAFE:/:SCHEMA: marker spec     | Adding intent markers, QR validation of markers         |
| `severity.md`       | MUST/SHOULD/COULD severity definitions   | Understanding QR severity, writing QR scripts           |
| `structural.md`     | Code quality conventions, testing rules  | QR code review, planner decision audit                  |
| `temporal.md`       | Timeless present rule for comments       | TW/QR temporal contamination checks, writing comments   |
| `diff-format.md`    | Unified diff spec for code changes       | Writing code diffs, Developer/QR diff validation        |
| `producer-validator.md` | Rewrite-or-loop-back review semantics | QR finding classification, planner QR gates             |
| `intake.md`         | Gather→Deepen→Summarize elicitation      | Planner intake phases, any skill needing requirements   |
| `visualization.md`  | Mermaid diagram-slot rules + suppression | Planner design diagrams, TW diagram authoring, QR grounding |
| `milestones.md`     | Milestone soundness criteria + Outcome schema | Planner milestones mode, cross-milestone learning  |
| `core-flows.md`     | Frozen SEQ-only behavioral spec, produced before structural design | Planner initiative mode, behavioral-spec phase |
| `tech-plan.md`      | Structural architecture artifact (CON/CMP/Data-Model) + dedicated adversarial review | Planner initiative mode, tech-plan spec/review phases |
| `artifacts.md`          | Artifact lifetime taxonomy (frozen/additive-forward/disposable) + per-artifact class table | Understanding artifact lifecycle, planner phase authoring, QR grounding |
| `guided-transitions.md` | Auto-advance vs hand-back transition discipline; review/interactive phases always park | Understanding phase-transition rationale, planner/discovery/curation flow design |

## Subdirectories

| Directory       | What                                   | When to read                                                       |
| --------------- | -------------------------------------- | ------------------------------------------------------------------ |
| `code-quality/` | Baseline/split/drift quality checks    | Design, code review, refactoring, planning-time quality validation |
