# workflow/

Workflow orchestration framework: types, discovery, and the durable persistence substrate.

## Architecture

Skills use CLI-based step invocation. The workflow flow is:

```
main() -> format_output() -> print() -> LLM reads -> follows <invoke_after>
```

Workflow/StepDef are metadata containers for introspection. The execution engine
(Workflow.run(), Outcome, StepContext) was removed as dead code.

## Files

| File           | What                                      | When to read                                        |
| -------------- | ----------------------------------------- | --------------------------------------------------- |
| `core.py`      | Workflow, StepDef, Arg (metadata only)    | Defining new skills, workflow structure             |
| `discovery.py` | Workflow discovery via importlib scanning | Understanding pull-based discovery, troubleshooting |
| `__init__.py`  | Public API exports                        | Importing workflow types                            |
| `cli.py`       | CLI helpers for workflow entry points     | Adding CLI arguments, step output helpers           |
| `constants.py` | Shared constants, QR constants re-exports | Adding new constants                                |
| `types.py`     | Domain types: Dispatch, AgentRole, etc.   | QR gates, sub-agent dispatch, test domains          |

## Subdirectories

| Directory       | What                                                            | When to read                                        |
| --------------- | --------------------------------------------------------------- | --------------------------------------------------- |
| `persistence/`  | Durable event-sourcing substrate for skill runs                 | Run dirs, event log, projection, resume, retention  |
| `prompts/`      | Step prompt wrappers for the remaining Python-CLI skills         | Editing CLI-skill step output                        |
| `formatters/`   | Legacy no-export stub; deletion gated on parity R-004 (DL-008)  | Removing the Python-CLI step layer (M-008b)          |

## Test

```bash
pytest tests/ -v
pytest tests/ -k deepthink -v
```
