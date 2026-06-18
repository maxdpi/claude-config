/**
 * arxiv-to-md — Workflow-tool port (M-006, CI-M-006-009).
 *
 * Replaces the 3-step --step re-invocation loop with native sequential phases
 * + parallel() fan-out via the Workflow tool (one converter agent per paper).
 *
 * Both invocation modes are preserved (domain logic from
 * skills/scripts/skills/arxiv_to_md/main.py):
 *
 *   MODE 1 (direct conversion):
 *     User provides arXiv IDs → parallel converter agents → finalize filenames
 *
 *   MODE 2 (PDF folder sync):
 *     User specifies source PDF folder + destination markdown folder
 *     Scan existing .md files, skip matches, resolve IDs for gaps → parallel convert
 *
 * converter agents write files and run under isolation:worktree (DL-018).
 * permissionMode / maxTurns / skills live on agents/converter.md (DL-023).
 */

export const meta = {
  name: "arxiv-to-md",
  description: "Convert arXiv papers to LLM-consumable markdown",
  phases: ["discover", "convert", "finalize"],
  /**
   * Phase trust manifest (DL-014, DL-006).
   * Consumed by the hook-driven bridge (workflow_bridge.py) to populate manifest.json.
   * NOTE: the AUTHORITATIVE phase record is the hook bridge, not the DURABLE_EVENT
   * log() lines. The log lines are human breadcrumbs only.
   *
   * Discover is read_only (scan + lookup). Convert/finalize write files.
   */
  phaseTrust: {
    "discover": "read_only",
    "convert":  "write",
    "finalize": "write",
  },
};

  // ── Phase 1: Discover ─────────────────────────────────────────────────────
  phase("discover");

  const discoverResult = await agent(
    `ARXIV-TO-MD — Discover and Dispatch

MODE DETECTION:
Determine which mode based on user input:

MODE 1 (default): Direct conversion
  Trigger: User provides arXiv IDs directly, or asks to convert papers
  Filename: Orchestrator constructs from paper title + date

MODE 2: PDF folder sync
  Trigger: User specifies source PDF folder AND destination markdown folder
  Filename: Derived from PDF filename

============================================================

MODE 1 DISCOVERY:
Before asking the user for arXiv IDs, check for:
  - CLAUDE.md in current directory (may list arXiv IDs)
  - README.md or similar docs with arXiv links/IDs
  - .bib files with arXiv entries
If IDs found, confirm with user: 'Found arXiv ID(s) X, Y. Convert these?'

PARSE USER INPUT:
If user provides input directly, parse for arXiv IDs:
  - Format: YYMM.NNNNN (e.g., 2503.05179)
  - Or full URL: https://arxiv.org/abs/YYMM.NNNNN
  - May be multiple IDs

============================================================

MODE 2 DISCOVERY (PDF folder sync):

FORBIDDEN - NEVER read PDF files.

CRITICAL - CHECK EXISTING FILES FIRST:
Most files WILL already exist. Skipping is the common case.
Before dispatching ANY converter, check if output already exists.

FILE NAMING CONVENTION:
  PDFs:     YYYY-MM-DD <title>.pdf
  Markdown: YYYY-MM-DD <title>.md

1. SCAN DESTINATION FOLDER for existing markdown FIRST
2. SCAN SOURCE FOLDER for PDFs
3. For EACH PDF, check if matching .md exists — if so, SKIP
4. RESOLVE ARXIV IDs from unmatched PDFs via WebSearch (do NOT read PDFs)
5. DETERMINE DESTINATION FILENAMES for unmatched PDFs

============================================================

Output as JSON:
{
  "mode": 1,
  "papers": [
    {"arxiv_id": "2503.05179", "dest_file": null},
    ...
  ],
  "skipped": ["2501.00001", ...]
}

For MODE 2:
{
  "mode": 2,
  "papers": [
    {"arxiv_id": "2503.05179", "dest_file": "/path/to/dest/2025-03-07 Title.md"},
    ...
  ],
  "skipped": ["2501.00001", ...]
}`,
    {
      label: "discover",
      phase: "discover",
      schema: {
        type: "object",
        properties: {
          mode:    { type: "integer" },
          papers:  {
            type: "array",
            items: {
              type: "object",
              properties: {
                arxiv_id:  { type: "string" },
                dest_file: { type: ["string", "null"] },
              },
              required: ["arxiv_id"],
            },
          },
          skipped: { type: "array", items: { type: "string" } },
        },
        required: ["mode", "papers"],
      },
    },
  );

  let mode    = discoverResult?.mode    ?? 1;
  let papers  = discoverResult?.papers  ?? [];
  let skipped = discoverResult?.skipped ?? [];

  log(`Mode ${mode}: ${papers.length} paper(s) to convert, ${skipped.length} skipped`);

  if (papers.length === 0) {
    log("No papers to convert. Done.");
    return {
      markdown: { converted: [], skipped, failed: [] },
    };
  }

  // ── Phase 2: Convert (parallel, one converter per paper) ─────────────────
  phase("convert");

  const convertResults = await parallel(
    papers.map((paper) => () => {
      const destClause = paper.dest_file
        ? `\nDestination file: ${paper.dest_file}`
        : "";
      return agent(
        `ARXIV-TO-MD — Convert paper

arXiv ID: ${paper.arxiv_id}${destClause}

You are converting this arXiv paper to clean markdown.

Steps:
1. Fetch TeX source from https://arxiv.org/e-print/${paper.arxiv_id}
2. Extract and locate main .tex file from the tarball
3. Convert to markdown:
   - Preserve section hierarchy as # ## ### headings
   - Convert equations to LaTeX math ($...$ inline, $$...$$ display)
   - Convert figures to descriptive captions
   - Convert tables to markdown tables
   - Remove TeX boilerplate (preamble, \\bibliography commands)
   - Preserve abstract, sections, conclusion
   - Keep citations as [Author, Year]
4. Write cleaned markdown to /tmp/arxiv_${paper.arxiv_id}/cleaned.md
5. Report result:
${
  paper.dest_file
    ? `   On success: FILE: /tmp/arxiv_${paper.arxiv_id}/cleaned.md`
    : `   On success:\n   FILE: /tmp/arxiv_${paper.arxiv_id}/cleaned.md\n   TITLE: <paper title>\n   DATE: <YYYY-MM-DD>`
}
   On failure: FAIL: <reason>`,
        {
          label: `convert-${paper.arxiv_id}`,
          phase: "convert",
          agentType: "developer",
          isolation: "worktree",
        },
      );
    }),
  );

  // Pair results with papers
  const conversions = papers.map((paper, i) => ({
    arxiv_id: paper.arxiv_id,
    dest_file: paper.dest_file,
    result: convertResults[i],
  }));

  // ── Phase 3: Finalize ─────────────────────────────────────────────────────
  phase("finalize");

  const finalizeResult = await agent(
    `ARXIV-TO-MD — Finalize

Mode: ${mode}

Conversion results:
${JSON.stringify(conversions, null, 2)}

For each SUCCESSFUL conversion:

MODE 1 (dest_file is null — construct filename from metadata):
1. CONSTRUCT FILENAME:
   Format: YYYY-MM-DD Title - Subtitle.md
   a) Start with DATE from converter
   b) Take TITLE from converter
   c) Replace ? ; : with ' - '
   d) Remove unsafe chars: / \\ < > | " *
   e) Collapse multiple spaces to single space
   f) Concatenate: '<date> <title>.md'
   FALLBACK: If title/date missing, use <arxiv_id>.md

2. Copy: cp /tmp/arxiv_<id>/cleaned.md './<constructed_filename>'

MODE 2 (dest_file provided — copy to pre-determined destination):
1. Copy: cp /tmp/arxiv_<id>/cleaned.md '<dest_file>'

VERIFICATION: Use Read tool to confirm file exists and has content.

PRESENT FINAL SUMMARY to user:
Processed M PDFs: N converted, K skipped (already exist), F failed

Skipped (already exist):
  <arxiv_id> -> already exists

Converted:
  [OK] <arxiv_id> -> ./<filename>

Failed:
  [FAIL] <arxiv_id> -> <reason>`,
    { label: "finalize", phase: "finalize" },
  );

  // Parse summary for the return artifact
  const converted = conversions
    .filter((c) => !c.result?.startsWith?.("FAIL"))
    .map((c) => c.arxiv_id);
  const failed = conversions
    .filter((c) => c.result?.startsWith?.("FAIL"))
    .map((c) => ({ arxiv_id: c.arxiv_id, reason: c.result }));

  return {
    markdown: {
      converted,
      skipped,
      failed,
      summary: finalizeResult,
    },
  };
