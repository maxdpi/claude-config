# prompts/

Plain-text prompt building blocks for workflows: file embedding and step assembly.

## Files

| File          | What                                                                             | When to read                                          |
| ------------- | -------------------------------------------------------------------------------- | ----------------------------------------------------- |
| `__init__.py` | Package exports for `format_file_content` and `format_step`                     | Importing prompt utilities                            |
| `file.py`     | `format_file_content()` — 4-backtick fence embedding (safe for nested triple-backtick content) | Embedding file content in prompts, modifying fence style |
| `step.py`     | `format_step()` — sole assembler for step output including `invoke_after` logic  | Assembling step output, modifying step format         |
