---
name: arxiv-to-md
description: Convert arXiv papers to LLM-consumable markdown. Invoke when user provides an arXiv ID or URL, or when syncing academic papers from a PDF folder to a markdown destination.
---

# arXiv to Markdown

Convert arXiv papers (TeX source) to clean markdown for LLM consumption.

## Invocation

Invoke the Workflow tool with the script at `skills/arxiv-to-md/workflow.mjs`. Pass the user's request (arXiv ID, URL, or folder path) as `args`.

The workflow handles both single-paper and batch-folder modes natively.

Do NOT explore or analyze first. Invoke the workflow and follow its phases.
