<!-- /runs -- list durable skill runs. No arguments. See also: /run-status, /resume. -->
<!-- Source: skills.lib.workflow.persistence.registry.list_runs() (ref: DL-003) -->
List all skill runs from the durable registry.

Run the following Python command and present its output as a table:

```bash
python3 -c "
import sys
sys.path.insert(0, '$HOME/.claude/skills/scripts')
from skills.lib.workflow.persistence.registry import list_runs
import datetime, time

runs = list_runs()
if not runs:
    print('No skill runs found.')
else:
    print(f'{\"ID\":<12} {\"SKILL\":<22} {\"STATUS\":<12} {\"PHASE\":<18} AGE')
    print('-' * 72)
    for r in runs:
        started = r.get('started_at') or ''
        age = '-'
        if started:
            try:
                dt = datetime.datetime.fromisoformat(started)
                secs = time.time() - dt.timestamp()
                h = int(secs // 3600)
                m = int((secs % 3600) // 60)
                age = f'{h}h{m:02d}m' if h else f'{m}m'
            except Exception:
                age = '?'
        run_id = r.get('run_id', '')
        skill = r.get('skill') or 'unknown'
        status = r.get('status', 'unknown')
        phase = r.get('active_phase') or '-'
        print(f'{run_id[:12]:<12} {skill[:22]:<22} {status:<12} {phase[:18]:<18} {age}')
"
```

**Status key:**
- `running` — active or interrupted (use `/resume <id>` to continue)
- `crashed` — terminated unexpectedly (use `/resume <id>` to continue)
- `done` — completed successfully
- `tombstoned` — explicitly closed
