#!/usr/bin/env python3
"""Crash/chaos tests for the durable-substrate persistence core.

These tests use only stdlib (multiprocessing, subprocess, os, signal) so
they run in the default pytest suite without any extra dependencies.

Coverage
--------
1. Scaled concurrent append: 50–100 processes writing to ONE run dir under
   flock; assert no torn lines, exact event count, serial-fold equivalence.
2. Atomic-write crash injection: child processes killed at three crash points;
   parent asserts target .json is never torn or empty, replay always succeeds.
3. Append durability under SIGKILL: writer subprocess killed mid-stream;
   events.jsonl has only whole lines and replay succeeds.
"""
from __future__ import annotations

import json
import multiprocessing
import os
import signal
import sys
import tempfile
import textwrap
import time
import uuid
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Make the persistence package importable
# ---------------------------------------------------------------------------

_SCRIPTS = Path(__file__).parent.parent / "skills" / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from skills.lib.workflow.persistence import (
    EVENT_PHASE_STARTED,
    EVENT_RUN_STARTED,
    append_event,
    create_run_dir,
    empty_projection,
    event_schema,
    fold,
    replay,
    write_atomic,
)
from skills.lib.workflow.persistence.eventlog import _replay_from_path
from skills.lib.workflow.persistence.rundir import RunDir


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def tmp_base(tmp_path: Path) -> Path:
    return tmp_path / "skill-runs"


@pytest.fixture
def run_dir(tmp_base: Path):
    return create_run_dir(skill="chaos-test", base_dir=tmp_base)


# ---------------------------------------------------------------------------
# Worker helpers (module-level so they can be pickled by multiprocessing)
# ---------------------------------------------------------------------------


def _concurrent_worker(run_dir_path: str, run_id: str, worker_id: int, n: int, payload_size: int) -> None:
    """Append n events with controlled payload size, then exit cleanly."""
    import sys as _sys
    _scripts = str(Path(__file__).parent.parent / "skills" / "scripts")
    if _scripts not in _sys.path:
        _sys.path.insert(0, _scripts)

    from skills.lib.workflow.persistence import append_event, event_schema, EVENT_PHASE_STARTED
    from skills.lib.workflow.persistence.rundir import RunDir
    from pathlib import Path as _Path

    base = _Path(run_dir_path).parent
    rd = RunDir(run_id=run_id, base=base)

    # Pad payload to test near-limit sizes
    padding = "x" * payload_size

    for i in range(n):
        ev = event_schema(
            type=EVENT_PHASE_STARTED,
            run_id=run_id,
            agent_id=f"w{worker_id}",
            payload={"phase_id": f"w{worker_id}-ev{i}", "pad": padding},
        )
        append_event(rd, ev)


# ---------------------------------------------------------------------------
# 1. Scaled concurrent append
# ---------------------------------------------------------------------------


class TestScaledConcurrentAppend:
    @pytest.mark.parametrize("n_workers,events_per_worker,payload_size", [
        (50, 2, 0),        # 100 events, minimal payload
        (20, 5, 512),      # 100 events, moderate payload
        (10, 5, 4096),     # 50 events, large payload
    ])
    def test_no_torn_lines_exact_count(
        self,
        run_dir,
        n_workers: int,
        events_per_worker: int,
        payload_size: int,
    ):
        """Concurrent appenders produce exactly the right count of whole JSON lines."""
        ctx = multiprocessing.get_context("spawn")
        procs = [
            ctx.Process(
                target=_concurrent_worker,
                args=(str(run_dir.path), run_dir.run_id, w, events_per_worker, payload_size),
            )
            for w in range(n_workers)
        ]
        for p in procs:
            p.start()
        for p in procs:
            p.join(timeout=60)
            assert p.exitcode == 0, f"Worker {p.pid} exited with code {p.exitcode}"

        raw = run_dir.events_jsonl.read_text(encoding="utf-8")
        lines = [ln for ln in raw.splitlines() if ln.strip()]
        expected = n_workers * events_per_worker

        # No torn lines: every line must be valid JSON
        for i, line in enumerate(lines):
            try:
                json.loads(line)
            except json.JSONDecodeError as exc:
                pytest.fail(
                    f"Line {i} is not valid JSON (torn write detected): {exc!r}\n"
                    f"Content: {line[:200]!r}"
                )

        # No lost updates
        assert len(lines) == expected, (
            f"Expected {expected} events; got {len(lines)} "
            f"(lost {expected - len(lines)} or gained {len(lines) - expected})"
        )

    def test_projection_equals_serial_fold_after_concurrent_appends(self, run_dir):
        """After concurrent appends, projection.json must equal serial fold of all events."""
        n_workers = 30
        events_per_worker = 3

        ctx = multiprocessing.get_context("spawn")
        procs = [
            ctx.Process(
                target=_concurrent_worker,
                args=(str(run_dir.path), run_dir.run_id, w, events_per_worker, 0),
            )
            for w in range(n_workers)
        ]
        for p in procs:
            p.start()
        for p in procs:
            p.join(timeout=60)

        # The replayed projection from events.jsonl must match projection.json
        stored = json.loads(run_dir.projection.read_text(encoding="utf-8"))
        replayed = replay(run_dir)

        assert json.dumps(stored, sort_keys=True) == json.dumps(replayed, sort_keys=True), (
            "projection.json diverged from serial replay after concurrent appends"
        )

        # Sanity: all events accounted for
        lines = [ln for ln in run_dir.events_jsonl.read_text().splitlines() if ln.strip()]
        assert len(lines) == n_workers * events_per_worker

    def test_near_limit_payload_no_torn_lines(self, run_dir):
        """Near-limit payloads (close to _MAX_EVENT_BYTES) must not tear lines."""
        # _MAX_EVENT_BYTES = 65536; use ~60KB to stay within truncation threshold
        payload_size = 60_000
        n_workers = 5
        events_per_worker = 2

        ctx = multiprocessing.get_context("spawn")
        procs = [
            ctx.Process(
                target=_concurrent_worker,
                args=(str(run_dir.path), run_dir.run_id, w, events_per_worker, payload_size),
            )
            for w in range(n_workers)
        ]
        for p in procs:
            p.start()
        for p in procs:
            p.join(timeout=60)

        lines = [ln for ln in run_dir.events_jsonl.read_text(encoding="utf-8").splitlines() if ln.strip()]

        # All lines must be valid JSON (no tearing even for large writes)
        for i, line in enumerate(lines):
            try:
                json.loads(line)
            except json.JSONDecodeError as exc:
                pytest.fail(f"Near-limit payload tore line {i}: {exc!r}")

        # Count matches (truncation is allowed by design; events are never lost)
        assert len(lines) == n_workers * events_per_worker


# ---------------------------------------------------------------------------
# 2. Atomic-write crash injection
# ---------------------------------------------------------------------------
#
# Strategy: run a small subprocess script that writes a tmp file and then
# calls os._exit() at a controlled crash point BEFORE os.rename completes.
# We then assert the target is either the intact old content or intact new
# content, and that replay still reconstructs a valid projection.
#
# Crash points:
#   A: after tmp written + fsynced, before os.rename
#   B: crash script writes, fsyncs, renames, then os._exit before dir-fsync
#   C: partial write of tmp (write half the bytes, then os._exit)

_CRASH_SCRIPT_TEMPLATE = textwrap.dedent("""\
    import os, sys, json, tempfile
    from pathlib import Path

    target = Path({target!r})
    data = {data!r}
    crash_point = {crash_point!r}

    payload = json.dumps(data, ensure_ascii=False, sort_keys=True).encode("utf-8")
    fd, tmp_path = tempfile.mkstemp(dir=str(target.parent), prefix=".tmp-crash-")

    if crash_point == "C":
        # Partial write: only write half the bytes, then kill
        half = len(payload) // 2
        os.write(fd, payload[:half])
        os.close(fd)
        os._exit(1)

    # Write full payload and fsync
    os.write(fd, payload)
    os.fsync(fd)
    os.close(fd)

    if crash_point == "A":
        # Crash after fsync but before rename — tmp exists, target unchanged
        os._exit(1)

    # Point B: rename (atomic), then crash before dir-fsync
    os.rename(tmp_path, str(target))
    os._exit(1)
""")


def _run_crash_subprocess(target_path: Path, new_data: dict, crash_point: str) -> None:
    """Launch a crash-injected subprocess for write_atomic."""
    import subprocess

    script = _CRASH_SCRIPT_TEMPLATE.format(
        target=str(target_path),
        data=new_data,
        crash_point=crash_point,
    )
    # Run as a subprocess so the os._exit() doesn't kill the test process
    proc = subprocess.run(
        [sys.executable, "-c", script],
        timeout=10,
    )
    # We expect the child to exit with code 1 (os._exit(1))
    assert proc.returncode == 1, f"Expected crash exit 1, got {proc.returncode}"


class TestAtomicWriteCrashInjection:
    @pytest.mark.parametrize("crash_point", ["A", "B", "C"])
    def test_target_intact_after_crash(self, tmp_path: Path, crash_point: str):
        """After a crash at point A/B/C, target.json is either old or new intact JSON."""
        target = tmp_path / "state.json"
        old_data = {"version": "old", "safe": True}
        new_data = {"version": "new", "safe": True}

        # Write known-good initial state via real write_atomic
        write_atomic(target, old_data)
        assert target.exists()
        assert json.loads(target.read_text()) == old_data

        # Inject crash
        _run_crash_subprocess(target, new_data, crash_point)

        # Target must be either old or new — never torn, never empty
        assert target.exists(), f"Target vanished after crash at point {crash_point}"
        raw = target.read_text(encoding="utf-8")
        assert raw.strip(), f"Target is empty after crash at point {crash_point}"

        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError as exc:
            pytest.fail(
                f"Target is torn/partial JSON after crash at point {crash_point}: "
                f"{exc!r}\nContent: {raw[:200]!r}"
            )

        # Must be EXACTLY old_data (crash A/C) or new_data (crash B after rename)
        assert parsed in (old_data, new_data), (
            f"Target contains unexpected data after crash at {crash_point}: {parsed!r}"
        )

    @pytest.mark.parametrize("crash_point", ["A", "B", "C"])
    def test_replay_succeeds_after_crash(self, tmp_path: Path, crash_point: str):
        """After a crash during projection write, replay reconstructs a valid projection."""
        base = tmp_path / "skill-runs"
        rd = create_run_dir(skill="crash-test", base_dir=base)

        # Append some real events to establish a good projection
        for i in range(3):
            ev = event_schema(
                EVENT_PHASE_STARTED,
                run_id=rd.run_id,
                payload={"phase_id": f"phase-{i}"},
            )
            append_event(rd, ev)

        good_projection = json.loads(rd.projection.read_text(encoding="utf-8"))

        # Inject a crash during projection.json rewrite
        new_data = {"corrupt_attempt": True, "version": 999}
        _run_crash_subprocess(rd.projection, new_data, crash_point)

        # replay() reads events.jsonl (never corrupted) and must succeed
        replayed = replay(rd)
        assert isinstance(replayed, dict), "replay() did not return a dict"
        assert "phases" in replayed, "replay() returned projection without 'phases'"

        # The replayed result must match what we had before (events.jsonl is intact)
        assert json.dumps(replayed, sort_keys=True) == json.dumps(good_projection, sort_keys=True), (
            f"replay() returned different projection after crash at {crash_point}"
        )

    def test_dangling_tmp_files_dont_corrupt_target(self, tmp_path: Path):
        """Dangling .tmp-crash-* files left by a crash never replace the target."""
        target = tmp_path / "projection.json"
        safe_data = {"status": "safe"}
        write_atomic(target, safe_data)

        # Simulate crash point A: tmp written but NOT renamed
        payload = json.dumps({"status": "corrupt"}).encode("utf-8")
        fd, tmp_path_str = tempfile.mkstemp(dir=str(tmp_path), prefix=".tmp-crash-")
        os.write(fd, payload)
        os.close(fd)
        # Do NOT rename — simulates crash before rename

        # Target must remain intact
        assert json.loads(target.read_text()) == safe_data, (
            "Dangling tmp file corrupted the target"
        )

        # Cleanup the dangling tmp
        os.unlink(tmp_path_str)


# ---------------------------------------------------------------------------
# 3. Append durability under SIGKILL
# ---------------------------------------------------------------------------

_WRITER_SCRIPT = textwrap.dedent("""\
    import sys, time
    from pathlib import Path

    _scripts = {scripts!r}
    if _scripts not in sys.path:
        sys.path.insert(0, _scripts)

    from skills.lib.workflow.persistence import append_event, event_schema, EVENT_PHASE_STARTED
    from skills.lib.workflow.persistence.rundir import RunDir

    base = Path({base!r})
    run_id = {run_id!r}
    rd = RunDir(run_id=run_id, base=base)

    i = 0
    while True:
        ev = event_schema(
            type=EVENT_PHASE_STARTED,
            run_id=run_id,
            payload={{"phase_id": f"ev-{{i}}"}},
        )
        append_event(rd, ev)
        i += 1
        # Brief pause to ensure the parent can SIGKILL mid-stream
        if i % 5 == 0:
            time.sleep(0.01)
""")


class TestSigkillDurability:
    def test_events_jsonl_intact_after_sigkill(self, tmp_base: Path):
        """After SIGKILL of a writer, events.jsonl has only whole lines and replay succeeds."""
        import subprocess

        rd = create_run_dir(skill="sigkill-test", base_dir=tmp_base)

        script = _WRITER_SCRIPT.format(
            scripts=str(_SCRIPTS),
            base=str(rd.base),
            run_id=rd.run_id,
        )

        proc = subprocess.Popen(
            [sys.executable, "-c", script],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

        # Let the writer run for a short time
        time.sleep(0.3)

        # SIGKILL — no cleanup possible
        proc.send_signal(signal.SIGKILL)
        proc.wait(timeout=5)

        # events.jsonl must contain only whole, parseable JSON lines
        raw = rd.events_jsonl.read_text(encoding="utf-8")
        lines = [ln for ln in raw.splitlines() if ln.strip()]

        for i, line in enumerate(lines):
            try:
                json.loads(line)
            except json.JSONDecodeError as exc:
                pytest.fail(
                    f"SIGKILL left a torn line at position {i}: {exc!r}\n"
                    f"Content: {line[:200]!r}"
                )

        # replay() must succeed regardless of how many events were written
        result = replay(rd)
        assert isinstance(result, dict), "replay() failed after SIGKILL"
        assert "phases" in result, "replay() returned projection without 'phases'"

    def test_sigkill_projection_never_torn(self, tmp_base: Path):
        """projection.json is never torn after SIGKILL because write_atomic uses rename."""
        import subprocess

        rd = create_run_dir(skill="sigkill-proj", base_dir=tmp_base)

        # Write an initial known-good projection
        initial_data = json.loads(rd.projection.read_text(encoding="utf-8"))

        script = _WRITER_SCRIPT.format(
            scripts=str(_SCRIPTS),
            base=str(rd.base),
            run_id=rd.run_id,
        )

        proc = subprocess.Popen(
            [sys.executable, "-c", script],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

        # Let a few rewrites happen
        time.sleep(0.25)
        proc.send_signal(signal.SIGKILL)
        proc.wait(timeout=5)

        # projection.json must be valid JSON (never torn)
        raw = rd.projection.read_text(encoding="utf-8")
        assert raw.strip(), "projection.json is empty after SIGKILL"
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError as exc:
            pytest.fail(f"projection.json is torn after SIGKILL: {exc!r}\nContent: {raw[:400]!r}")

        assert "phases" in parsed, "projection.json missing 'phases' after SIGKILL"
