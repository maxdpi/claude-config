<!-- /run-status <run_id_prefix> -- show state and projection for one run. -->
<!-- Source: skills.lib.workflow.persistence.projection.replay() (ref: DL-003) -->
Show the current state and projection for a skill run.

Usage: `/run-status <run_id_prefix>`

Run the following Python command, replacing `$ARGUMENTS` with the run ID prefix provided:

```bash
python3 -c "
import sys, json
sys.path.insert(0, '$HOME/.claude/skills/scripts')
from skills.lib.workflow.persistence.registry import list_runs, find_run
from skills.lib.workflow.persistence.projection import replay

prefix = '$ARGUMENTS'
if not prefix:
    print('Usage: /run-status <run_id_prefix>')
    sys.exit(1)

match = next((r for r in list_runs() if r['run_id'].startswith(prefix)), None)
if not match:
    print(f'No run found matching: {prefix}')
    sys.exit(1)

handle = find_run(match['run_id'])
if handle is None:
    print(f'Run directory not found for: {match[\"run_id\"]}')
    sys.exit(1)

run_dir = handle.as_run_dir()
projection = replay(run_dir)

print(f'Run ID    : {match[\"run_id\"]}')
print(f'Skill     : {match.get(\"skill\") or \"unknown\"}')
print(f'Status    : {match.get(\"status\", \"unknown\")}')
print(f'Phase     : {match.get(\"active_phase\") or \"-\"}')

phases = projection.get('phases') or {}
completed = [pid for pid, info in phases.items() if isinstance(info, dict) and info.get('status') == 'completed']
running = [pid for pid, info in phases.items() if isinstance(info, dict) and info.get('status') == 'running']
pending = [pid for pid, info in phases.items() if isinstance(info, dict) and info.get('status') not in ('completed', 'running')]

if completed:
    print(f'Completed : {', '.join(completed)}')
if running:
    print(f'Running   : {', '.join(running)}')
if pending:
    print(f'Pending   : {', '.join(pending)}')

tasks = projection.get('tasks') or {}
if tasks:
    done_count = sum(1 for t in tasks.values() if isinstance(t, dict) and t.get('status') == 'done')
    print(f'Tasks     : {done_count}/{len(tasks)} done')

subagents = projection.get('subagents') or {}
if subagents:
    print(f'Subagents : {len(subagents)}')

events_path = run_dir.events_jsonl
if events_path.exists():
    event_count = sum(1 for line in events_path.read_text(encoding='utf-8').splitlines() if line.strip())
    print(f'Events    : {event_count}')
"
```
