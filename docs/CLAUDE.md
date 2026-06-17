# docs/

## Files

| File                      | What                                                                    | When to read                                                         |
| ------------------------- | ----------------------------------------------------------------------- | -------------------------------------------------------------------- |
| `PLATFORM-ASSUMPTIONS.md` | M-000 validated platform assumptions (A1-A4) with confidence and proofs | Reviewing substrate design decisions, implementing resume or hooks   |
| `update_official_claude_docs.py` | uv script that re-fetches the official Claude Code docs from docs.anthropic.com via Jina Reader (needs `JINA_API_KEY`). Run with `-d 'docs/claude_code docs'` to refresh the vendored snapshot in place. | Refreshing the vendored `claude_code docs/` tree |
