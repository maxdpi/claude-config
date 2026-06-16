#!/usr/bin/env node
// M-000 / CI-M-000-001 -- Workflow-tool journal probe (assumption A1).
//
// A1: "Workflow tool journal entries are Python-readable and we can capture the
//      on-disk format/location (or record that they are not -> DL-013 fallback)."
//
// SHAPE OF THIS PROBE
// -------------------
// A Workflow-tool script cannot touch the filesystem (the runtime sandbox blocks
// fs/Node APIs), so a single .mjs cannot BOTH run inside the workflow AND read its
// own journal off disk. The probe is therefore split the way the milestone runs it:
//
//   1. The ORCHESTRATOR runs a minimal workflow via the Workflow tool. The exact
//      script used in M-000 is embedded below as MINIMAL_WORKFLOW_SOURCE.
//   2. THIS script (plain Node ESM, run with `node workflow_journal_probe.mjs`)
//      locates the journal that workflow wrote and validates that every line is
//      machine-readable JSON -- the property Python's json.loads needs.
//
// On 2026-06-16 step 1 was run with runId wf_f423bb66-344; this probe reads that
// run's journal back and confirms A1 holds (format documented in
// docs/PLATFORM-ASSUMPTIONS.md). DL-013 fallback is NOT selected.

import { readFileSync, readdirSync, statSync, existsSync } from 'node:fs';
import { join } from 'node:path';
import { homedir } from 'node:os';

// The minimal workflow the orchestrator runs (step 1). Kept here as the documented
// methodology -- run this via the Workflow tool, then point the probe at its runId.
export const MINIMAL_WORKFLOW_SOURCE = `export const meta = {
  name: 'm000-journal-probe',
  description: 'Minimal workflow that makes one agent() call so M-000 can locate and read its on-disk journal',
  phases: [{ title: 'Probe' }],
}
phase('Probe')
const r = await agent('Return the single word PONG and nothing else.', { label: 'journal-probe-ping' })
log('probe agent returned: ' + String(r).slice(0, 40))
return { probe: 'm000-journal', agentReturned: String(r).slice(0, 40) }`;

// Confirmed on-disk layout (2026-06-16). {project} is the cwd-derived project key,
// {sessionId} the CLI session, {runId} the wf_* id returned by the Workflow tool.
export const JOURNAL_LAYOUT = {
  journal: '~/.claude/projects/{project}/{sessionId}/subagents/workflows/{runId}/journal.jsonl',
  agentTranscript: '~/.claude/projects/{project}/{sessionId}/subagents/workflows/{runId}/agent-{agentId}.jsonl',
  agentMeta: '~/.claude/projects/{project}/{sessionId}/subagents/workflows/{runId}/agent-{agentId}.meta.json',
  runState: '~/.claude/projects/{project}/{sessionId}/workflows/{runId}.json',
  scriptFile: '~/.claude/projects/{project}/{sessionId}/workflows/scripts/{name}-{runId}.js',
};

const PROJECTS_ROOT = join(homedir(), '.claude', 'projects');

function findNewestJournal() {
  // Walk ~/.claude/projects/*/*/subagents/workflows/wf_*/journal.jsonl and return
  // the most recently modified one.
  let best = null;
  if (!existsSync(PROJECTS_ROOT)) return null;
  for (const project of safeReaddir(PROJECTS_ROOT)) {
    const sessRoot = join(PROJECTS_ROOT, project);
    for (const session of safeReaddir(sessRoot)) {
      const wfRoot = join(sessRoot, session, 'subagents', 'workflows');
      if (!existsSync(wfRoot)) continue;
      for (const run of safeReaddir(wfRoot)) {
        const j = join(wfRoot, run, 'journal.jsonl');
        if (!existsSync(j)) continue;
        const m = statSync(j).mtimeMs;
        if (!best || m > best.mtime) best = { path: j, mtime: m, runId: run, session, project };
      }
    }
  }
  return best;
}

function safeReaddir(p) {
  try { return readdirSync(p); } catch { return []; }
}

// probeWorkflowJournal(journalPath?) -> result object.
// Locates a Workflow journal (newest if not given), parses every line as JSON, and
// reports path + format + a sample entry. machineReadable === true validates A1.
export function probeWorkflowJournal(journalPath) {
  const located = journalPath
    ? { path: journalPath, runId: null, session: null, project: null }
    : findNewestJournal();

  if (!located) {
    return {
      probe: 'workflow_journal', assumption: 'A1',
      journalFound: false, machineReadable: false,
      verdict: 'NO_JOURNAL_FOUND',
      fallback: 'DL-013: if the journal is genuinely absent/opaque, ported skills must emit durable events directly to events.jsonl; the journal bridge becomes an optimization, not a correctness dependency.',
    };
  }

  const raw = readFileSync(located.path, 'utf8');
  const lines = raw.split('\n').filter((l) => l.trim().length > 0);
  const entries = [];
  let machineReadable = true;
  for (const line of lines) {
    try { entries.push(JSON.parse(line)); }
    catch { machineReadable = false; }
  }

  return {
    probe: 'workflow_journal', assumption: 'A1',
    journalFound: true,
    journalPath: located.path.replace(homedir(), '~'),
    runId: located.runId, session: located.session, project: located.project,
    lineCount: lines.length,
    machineReadable,
    entryTypes: [...new Set(entries.map((e) => e.type))],
    entryKeys: [...new Set(entries.flatMap((e) => Object.keys(e)))],
    sampleEntry: entries[0] ?? null,
    note: "journal line schema: {type:'started'|'result', key:'v2:<sha256>', agentId, result?}. `key` is the content-hash cache key resumeFromRunId matches on (same prompt+opts -> same key -> cache hit).",
    verdict: machineReadable ? 'A1_CONFIRMED' : 'A1_OPAQUE_USE_DL013_FALLBACK',
    fallbackSelected: machineReadable ? null : 'DL-013',
  };
}

// CLI entry: `node workflow_journal_probe.mjs [journalPath]`
if (import.meta.url === `file://${process.argv[1]}`) {
  const result = probeWorkflowJournal(process.argv[2]);
  console.log(JSON.stringify(result, null, 2));
  process.exit(result.machineReadable ? 0 : 1);
}
