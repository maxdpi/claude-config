---
name: arxiv-to-md
description: Convert arXiv papers to LLM-consumable markdown. Invoke when user provides an arXiv ID or URL, or when syncing academic papers from a PDF folder to a markdown destination.
---

# arXiv to Markdown

Convert arXiv papers (TeX source, or PDF fallback) to clean markdown for LLM
consumption.

## Prerequisites

Requires the `pandoc` binary on PATH (used for the TeX/PDF → markdown conversion).
Verify with `which pandoc` before invoking; if absent, install it first.

## Inputs (`args`)

One of:

- an **arXiv ID** (e.g. `2310.06825`) or **URL** → single-paper mode;
- a **folder path** of PDFs plus a markdown destination → batch-folder mode.

## Invocation

Invoke the Workflow tool with the script at `skills/arxiv-to-md/workflow.mjs`. Pass
the arXiv ID, URL, or folder path as `args`.

Do NOT explore or analyze first. Invoke the workflow and follow its phases.

## Workflow Phases

1. **discover** (read-only) — resolve the input to a work list; fetch TeX source
   when available, otherwise fall back to the PDF (papers without a source deposit
   are converted via pandoc from the PDF). In batch mode, one converter is
   dispatched per paper.
2. **convert** (write) — run pandoc to produce markdown, cleaning artifacts for
   LLM consumption.
3. **finalize** (write) — write the markdown to the destination.

## Output

A markdown file per paper at the destination path (single-paper mode writes one
file; batch mode writes one per source PDF).
