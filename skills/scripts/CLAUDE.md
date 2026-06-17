# scripts/

Python package root for all skill implementations, plus test configuration.

## Files

| File                      | What                                                      | When to read                                            |
| ------------------------- | --------------------------------------------------------- | ------------------------------------------------------- |
| `pytest.ini`              | pytest configuration: `pythonpath=.`, `testpaths=tests`   | Configuring test runs, adding test paths                |
| `validate_conventions.py` | CI script: validates `get_convention()` calls match `REGISTRY.yaml` | Running convention validation, debugging CI failures |

## Subdirectories

| Directory | What                                                         | When to read                                            |
| --------- | ------------------------------------------------------------ | ------------------------------------------------------- |
| `skills/` | Python package containing all skill implementations and `lib/` | Adding skills, modifying orchestration, importing types |
| `tests/`  | pytest test suite for skills                                 | Adding tests, debugging test failures                   |

## Test

```bash
cd skills/scripts && pytest tests/ -v
```
