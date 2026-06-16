# Property-Based and Chaos Testing

Two complementary test layers that deepen confidence in the concurrency,
atomicity, and purity guarantees of the durable-substrate persistence core.

## Files

| File | Depends on | Description |
|------|------------|-------------|
| `tests/test_property_substrate.py` | `hypothesis` | Fuzz fold purity, append/replay round-trips, classify\_phases security matrix, retention invariants |
| `tests/test_chaos_substrate.py` | stdlib only | Concurrent appends, atomic-write crash injection, SIGKILL durability |

## Dependency handling

The environment is PEP-668 externally-managed (system pip blocked).
Hypothesis must be installed in an isolated venv.

### Create the venv

```sh
python3 -m venv .venv
.venv/bin/pip install -r tests/requirements-dev.txt
```

`.venv/` is already listed in `.gitignore` — it will not be committed.

## Running the tests

### Property tests (requires hypothesis in venv)

```sh
.venv/bin/python -m pytest tests/test_property_substrate.py -v
```

### Chaos tests (stdlib only — no venv needed)

```sh
python3 -m pytest tests/test_chaos_substrate.py -v
```

### Default suite (chaos runs; property tests skip cleanly)

```sh
python3 -m pytest tests/ -q
```

Property tests emit `SKIPPED` (not `ERROR`) when hypothesis is absent.
Chaos tests always run because they use only stdlib.

## What is being tested

### Property tests (`test_property_substrate.py`)

**fold purity and determinism** (`TestFoldPurityAndDeterminism`)

- Generates random sequences of events mixing all known types plus unknown
  types with random extra payload fields.
- Asserts `fold` never mutates its input projection (deep-copy invariant).
- Asserts folding the same sequence twice yields identical projections.
- Asserts unknown event types leave the projection byte-for-byte unchanged
  (C-005 forward-compatibility).
- Asserts incremental fold equals single-pass replay.

**append->replay round-trip** (`TestAppendReplayRoundTrip`)

- Writes random event sequences through `append_event` to a tmp run dir.
- Asserts `replay(run_dir)` matches `projection.json` dict-for-dict.
- Asserts every line of `events.jsonl` is individually JSON-parseable.

**classify\_phases default-deny security matrix** (`TestClassifyPhasesDefaultDeny`)

- Fuzzes all combinations of phase tags (`read_only`/`write`/`execute`/untagged)
  against all parent permission modes (`plan`/`default`/`bypassPermissions`/
  `acceptEdits`/`auto`/unknown).
- Security invariants that must **always** hold:
  - A phase is `auto_replay` ONLY if its tag is `read_only` AND the parent
    mode is NOT in `{bypassPermissions, acceptEdits, auto}`.
  - `write`, `execute`, and untagged phases are always `needs_confirmation`.
  - Any overriding parent mode forces ALL phases to `needs_confirmation`.
  - Missing manifest (no tags) means all phases need confirmation (default-deny R-003).

**retention properties** (`TestRetentionProperties`)

- `prune_runs` deletes runs iff status ∈ {done, tombstoned, completed} AND
  age > TTL.
- Crashed/running/pending runs are NEVER deleted regardless of age (DL-005).
- `is_resumable(None)` is always `False`.
- `is_resumable` returns `True` iff a copied `transcript.jsonl` exists in
  the run subtree (primary path).

### Chaos tests (`test_chaos_substrate.py`)

**Scaled concurrent append** (`TestScaledConcurrentAppend`)

- Spawns 5–50 processes (multiprocessing spawn context) each appending K events
  to ONE run dir under the advisory flock.
- Asserts every line of `events.jsonl` is individually JSON-parseable (no torn lines).
- Asserts the event count is exactly `n_workers × events_per_worker` (no lost updates).
- Asserts `projection.json` equals a serial `replay()` of all events.
- Runs with minimal, moderate (~512B), large (~4KB), and near-limit (~60KB) payloads.

**Atomic-write crash injection** (`TestAtomicWriteCrashInjection`)

- Runs tiny subprocess scripts that crash (`os._exit(1)`) at three points:
  - **A**: after tmp written + fsynced, before `os.rename`
  - **B**: after `os.rename`, before dir-fsync
  - **C**: mid-write of tmp (only half the bytes)
- After each crash, asserts:
  - The target `.json` is either the intact old content or the intact new content
    (never torn or empty).
  - `replay()` still reconstructs a valid projection from the untouched `events.jsonl`.

**Append durability under SIGKILL** (`TestSigkillDurability`)

- Starts a writer subprocess appending events in a tight loop.
- Sends `SIGKILL` after a short delay.
- Asserts `events.jsonl` contains only whole JSON lines.
- Asserts `replay()` succeeds and returns a valid projection.
- Asserts `projection.json` is valid JSON (never torn, due to atomic rename).

## Hypothesis settings

Property tests use `max_examples=100–300` per property with
`suppress_health_check=[HealthCheck.too_slow]` to accommodate the filesystem
I/O inside some strategies. The `.hypothesis/` database is gitignored; shrunk
failing examples are stored there locally for fast regression.

## Interpreting results

A real bug surfaced by these tests would manifest as:

- A torn line in `events.jsonl` → concurrency/O\_APPEND regression.
- A lost update (fewer events than expected) → flock regression.
- `projection.json` diverging from `replay()` → atomic write or fold regression.
- Any phase classified `auto_replay` when it should be `needs_confirmation` →
  **security regression** (classify\_phases default-deny violation).
- A non-prunable run deleted → DL-005 retention regression.
