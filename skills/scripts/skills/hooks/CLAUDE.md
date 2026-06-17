# hooks/

Claude Code hook entrypoints invoked by the CC hook system on lifecycle events.

## Files

| File                   | What                                                                          | When to read                                                       |
| ---------------------- | ----------------------------------------------------------------------------- | ------------------------------------------------------------------ |
| `__init__.py`          | Package marker                                                                | -                                                                  |
| `run_event_hook.py`    | Hook for `TaskCreated`, `TaskCompleted`, `TeammateIdle`, `SubagentStop` events — routes to `teams_bridge` or `workflow_bridge` | Modifying hook dispatch, debugging Agent Teams capture |
| `session_end_hook.py`  | `SessionEnd` hook — flushes run state before runtime dirs are reaped          | Modifying session-end flush, debugging crash recovery (DL-002)     |
| `session_start_hook.py`| `SessionStart` hook — surfaces crash-recovery offers, prunes expired runs     | Modifying recovery UX, debugging TTL pruning (DL-002/DL-005)       |
| `subagent_start_hook.py` | `SubagentStart` hook — correlation and audit mirror for SubagentStop         | Modifying subagent correlation, debugging spawn tracking           |
