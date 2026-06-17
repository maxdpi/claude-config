# commands/

Slash-command definitions that expose the durable skill-run store.

## Files

| File            | What                                                                    | When to read                                              |
| --------------- | ----------------------------------------------------------------------- | --------------------------------------------------------- |
| `resume.md`     | `/resume` command: phase-aware resume with consent gate logic           | Modifying resume behavior, debugging resume flow          |
| `run-status.md` | `/run-status` command: show state and phase projection for one run      | Modifying run-status output, debugging projection display |
| `runs.md`       | `/runs` command: list all skill runs from the durable registry as table | Modifying runs listing, adding status key entries         |
