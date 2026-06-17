# fixtures/

Golden JSON parity fixtures for adversarial skill and workflow port contract tests,
plus representative Agent Teams `config.json` fixtures for the teams-bridge tests.

## Files

| File | What | When to read |
| ---- | ---- | ------------ |
| `real_team_config_multi.json` | Representative team `config.json` (lead + `researcher` challenger + `quality-reviewer` verifier) consumed by `test_teams_config_c1.py` to verify membership parsing | Modifying `teams_bridge.py` membership reads, debugging C1 roster capture |
| `real_team_config_lead_only.json` | Minimal team `config.json` (lead only) edge-case fixture | Testing the no-teammates path in `teams_bridge.py` |

## Subdirectories

| Directory | What | When to read |
| --------- | ---- | ------------ |
| `adversarial_skill_parity/` | Output equivalence fixtures for the three adversarial skill ports; consumed by `test_adversarial_skill_parity.py` | Understanding expected adversarial skill output contracts, regenerating fixtures for M-008b |
| `workflow_port_parity/` | Output equivalence fixtures for the seven linear workflow skill ports; consumed by `test_workflow_port_parity.py` | Understanding expected workflow port output contracts, regenerating fixtures |
