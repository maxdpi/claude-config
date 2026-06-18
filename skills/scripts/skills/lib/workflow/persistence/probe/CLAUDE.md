# probe/

Environment-capability probes that validate runtime assumptions before the substrate relies on them. Each probe ships with a `*_result.json` capturing the last recorded output.

## Files

| File                                    | What                                                                              | When to read                                                     |
| --------------------------------------- | --------------------------------------------------------------------------------- | ---------------------------------------------------------------- |
| `send_message_gate_probe.py`            | DL-031 probe (A4): whether the `SendMessage` tool is invocable only when Agent Teams is enabled | Debugging SendMessage availability gating, reviewing DL-031 assumption |
| `send_message_gate_probe_result.json`   | Captured output of the DL-031 probe run — never edit directly                    | Reviewing DL-031 probe results without re-running                |
| `subagent_transcript_probe.py`          | A4 probe: validates native subagent transcript path (`~/.claude/projects/.../subagents/agent-{agentId}.jsonl`) | Debugging transcript correlation, reviewing A4 assumption        |
| `subagent_transcript_probe_result.json` | Captured output of the A4 probe run — never edit directly                        | Reviewing A4 probe results without re-running                    |
| `teammate_memory_probe.py`              | DL-023 probe: validates whether `memory:` frontmatter is honored for Agent Teams teammates | Debugging teammate memory behavior, reviewing DL-023 assumption |
| `teammate_memory_probe_result.json`     | Captured output of the DL-023 probe run — never edit directly                    | Reviewing DL-023 probe results without re-running               |
| `teams_dir_probe.py`                    | A3 probe: validates `~/.claude/teams` and `~/.claude/tasks` ephemerality at session end | Debugging team-dir cleanup, reviewing A3 assumption              |
| `workflow_journal_probe.mjs`            | A1 probe: validates Workflow-tool journal entry format and on-disk location       | Debugging journal-to-substrate sync, reviewing A1 assumption     |
| `pipeline_probe.py`                     | DL-T1-05 probe: verifies pipeline() availability on the Workflow tool and whether /tmp artifacts survive worktree isolation into a downstream stage — gates M-006 arxiv restructuring | Auditing pipeline() availability constraints; reviewing DL-T1-05 gate decision |
| `pipeline_probe_result.json`            | Captured output of the DL-T1-05 probe run — never edit directly                  | Reviewing M-001 probe result without re-running                  |
