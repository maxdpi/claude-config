# tests/

Test suite for the durable-substrate persistence core and native-runtime skill ports.

## Files

| File | What | When to read |
| ---- | ---- | ------------ |
| `PROPERTY_TESTING.md` | Setup guide for property-based and chaos tests; venv creation, run commands, invariant descriptions | Setting up hypothesis venv, understanding property/chaos test coverage, debugging test failures |
| `requirements-dev.txt` | Dev dependencies (`hypothesis`, `pytest`) for the isolated `.venv` | Creating the venv, adding test dependencies |
| `test_adversarial_skill_parity.py` | M-007 parity gate: output equivalence of adversarial skill ports (decision-critic, deepthink, problem-analysis) against Python predecessors using golden fixtures | Verifying adversarial port correctness, debugging parity failures before M-008b deletion |
| `test_chaos_substrate.py` | Crash/chaos tests: concurrent append (50–100 processes), atomic-write crash injection, SIGKILL durability — stdlib only, no extra deps | Debugging concurrency or atomicity regressions in the persistence core |
| `test_contract_registry_retention.py` | M-002 acceptance tests: directory-as-contract, run registry scanning, retention TTL, resume age-guard | Modifying retention logic, debugging registry or TTL behavior |
| `test_hook_adapters.py` | M-003 acceptance tests: hook adapters, `run_event_hook`, session hooks, quarantine on unmatched payload | Modifying hook adapter logic, debugging event classification |
| `test_persistence_core.py` | M-001 acceptance tests: fold/replay determinism, concurrent appends under flock, phase manifests, retention prune | Modifying persistence core, debugging fold/replay divergence |
| `test_platform_assumptions.py` | M-000 pinned platform assumptions (A1–A4): Workflow journal, Agent Teams dirs, subagent transcript shape | Investigating platform-level regressions, understanding load-bearing assumptions |
| `test_property_substrate.py` | Property-based (Hypothesis) tests: fold purity, append/replay round-trips, `classify_phases` default-deny security matrix, retention invariants | Running fuzz coverage on the substrate, debugging security matrix regressions; requires `.venv` |
| `test_resume.py` | M-004 acceptance tests: `classify_phases`, `compute_remaining_tasks`, DL-021 permission-mode override, default-deny for untagged phases | Modifying resume engine, debugging phase classification or DL-021 override |
| `test_static_integrity.py` | Static structural checks for the native-runtime migration: verifies 7 linear skills have `workflow.mjs`, 3 adversarial skills have `SKILL.md`, no `team.md` construct | Verifying skill ports are structurally complete, adding new skills |
| `test_structural_parity.py` | Structural-contract parity: phase sequence, exploration fan-out, output schema keys match between Python predecessor and `.mjs` port | Catching silent structural regressions in ported skills |
| `test_team_mode_fallback.py` | M-007 fallback tests: `select_orchestration_mode` env-var detection, same durable events on both paths, no writes to `~/.claude/teams` or `~/.claude/tasks` | Debugging orchestration mode selection, verifying fallback parity |
| `test_teams_bridge.py` | Agent Teams durable-substrate bridge tests: team run creation from live hook stream, assumed field-name constants, idempotency | Modifying `teams_bridge.py`, debugging team run capture |
| `test_workflow_bridge.py` | Workflow run-state bridge tests: deterministic `run_id`, phase manifest, `classify_phases`, idempotency, partial-run resumability | Modifying `workflow_bridge.py`, debugging bridge correctness |
| `test_workflow_port_parity.py` | M-006/M-006.5 parity tests: journal/eventlog divergence detection (CI-M-006-005), workflow-port output parity via golden fixtures (CI-M-006-008) | Debugging stale-eventlog resume bugs, verifying workflow port output |

## Subdirectories

| Directory | What | When to read |
| --------- | ---- | ------------ |
| `fixtures/` | Golden JSON parity fixtures for adversarial skill and workflow port tests | Understanding expected output contracts, regenerating fixtures |
| `live/` | Manual live-session test kit: runbook, debug hook, assert scripts for validating against a real `~/.claude` install | Running live validation scenarios (S1–S5), debugging production hook behavior |
| `tools/` | Development tools: MJS syntax checker and skill structure extractor | Validating workflow.mjs syntax, extracting skill structure for parity checks |

## Test Execution

```bash
# Default suite (chaos runs; property tests skip cleanly without hypothesis)
python3 -m pytest tests/ -q

# Property tests (requires .venv from PROPERTY_TESTING.md)
.venv/bin/python -m pytest tests/test_property_substrate.py -v

# Chaos tests (stdlib only)
python3 -m pytest tests/test_chaos_substrate.py -v
```
