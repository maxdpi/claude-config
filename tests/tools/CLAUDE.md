# tools/

Development tools for validating native-runtime skill structure.

## Files

| File | What | When to read |
| ---- | ---- | ------------ |
| `check_mjs_syntax.sh` | Validates every `skills/*/workflow.mjs` in the Workflow-tool dialect (wraps body in async function before checking; rejects stray `export` beyond `meta`); prints PASS/FAIL per file, exits non-zero on any failure | Validating MJS syntax after modifying or adding a `workflow.mjs`, debugging syntax check failures |
| `extract_skill_structure.py` | Extracts structural contract (phase sequence, fan-out shape, output schema keys) from both Python predecessor skills and `.mjs` ports; used by `test_structural_parity.py` | Understanding how structural parity extraction works, adding new skills to the parity suite |
