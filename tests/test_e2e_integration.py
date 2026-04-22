#!/usr/bin/env python3
"""
End-to-end integration tests for the Mini-Savi data flow pipeline.

Validates the complete chain without requiring root or Mininet:
  coverage injection -> file creation -> JSON parsing -> FRR-P4 sync -> terminal management
"""

import json
import os
import shutil
import struct
import sys
import tempfile
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from coverage_injector import CoverageInjector
from receive_grid_coverage_data import (
    GCOV_BINARY_HDR_FORMAT,
    GCOV_BINARY_HDR_SIZE,
    GCOV_MSG_DELTA,
    GCOV_MSG_FULL,
    GridCoverageAnalyzer,
    GridType,
    _binary_state,
    process_binary_message,
)
from frr_to_p4_sync import (
    FRRRouteEntry,
    P4TableEntry,
    ip_to_mac,
    lcsa_to_p4_entries,
    parse_isis_database_lcsa,
    parse_isis_routes,
    prefix_to_lpm,
    routes_to_p4_entries,
)
from terminal_location import TerminalLocationManager, TerminalState

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_binary_msg(msg_type, sat_id, seq, ts, add_codes, rm_codes=()):
    """Build a binary coverage message from components."""
    add_count = len(add_codes)
    rm_count = len(rm_codes)
    hdr = struct.pack(GCOV_BINARY_HDR_FORMAT, msg_type, sat_id, seq, ts,
                      add_count, rm_count)
    body = struct.pack(f'<{add_count}I', *add_codes) if add_count else b''
    body += struct.pack(f'<{rm_count}I', *rm_codes) if rm_count else b''
    return hdr + body


# ===========================================================================
# Test 1: Full Coverage Pipeline
# ===========================================================================

class TestFullCoveragePipeline:
    """Inject coverage for 5 satellites, verify files, summary, and parsing."""

    def setup_method(self):
        self.tmpdir = Path(tempfile.mkdtemp(prefix="cov-pipeline-"))
        self.injector = CoverageInjector(
            state_dir=self.tmpdir, throttle_interval=0.0
        )

    def teardown_method(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_full_pipeline(self):
        sat_grids = {
            "1": [f"F00_{i}" for i in range(10)],
            "2": [f"F01_{i}" for i in range(8)],
            "3": [f"F02_{i}" for i in range(12)],
            "4": [f"LAT10_LON{i}" for i in range(6)],
            "5": [f"LAT20_LON{i}" for i in range(9)],
        }

        # Step 1 & 2: inject and verify individual files
        for sat_id, grids in sat_grids.items():
            ok = self.injector.inject_coverage(sat_id, grids)
            assert ok, f"Injection failed for sat {sat_id}"

        for sat_id, grids in sat_grids.items():
            fpath = self.tmpdir / f"sat_{sat_id}.json"
            assert fpath.exists(), f"Missing file for sat {sat_id}"
            data = json.loads(fpath.read_text())
            assert data["satellite_id"] == sat_id
            assert data["grid_codes"] == grids
            assert data["grid_count"] == len(grids)
            assert "timestamp" in data

        # Step 3: write and verify summary
        self.injector.write_summary_file()
        summary_path = self.tmpdir / "summary.json"
        assert summary_path.exists()
        summary = json.loads(summary_path.read_text())
        assert set(summary.keys()) == set(sat_grids.keys())
        for sat_id in sat_grids:
            assert summary[sat_id]["grid_count"] == len(sat_grids[sat_id])

        # Step 4: simulate isis_lcsa.c reading each file
        for sat_id in sat_grids:
            fpath = self.tmpdir / f"sat_{sat_id}.json"
            raw = fpath.read_text()
            parsed = json.loads(raw)
            assert parsed["coverage_state"] == "current"
            assert isinstance(parsed["grid_codes"], list)
            assert isinstance(parsed["timestamp"], float)

        # Step 5: cleanup
        self.injector.cleanup()
        remaining = list(self.tmpdir.glob("sat_*.json"))
        assert len(remaining) == 0
        assert not (self.tmpdir / "summary.json").exists()

        stats = self.injector.get_statistics()
        assert stats["inject_count"] == 5
        assert stats["error_count"] == 0

# ===========================================================================
# Test 2: Binary Protocol End-to-End
# ===========================================================================

class TestBinaryProtocolE2E:
    """Simulate a satellite's coverage evolution via binary messages."""

    def setup_method(self):
        # Clear global binary state for isolation
        _binary_state.clear()
        self.analyzer = GridCoverageAnalyzer(
            enable_frr_injection=False
        )

    def teardown_method(self):
        _binary_state.clear()

    def test_binary_evolution(self):
        SAT = 42

        # t=0: Full message with 20 grids
        full_grids_0 = list(range(1000, 1020))
        msg0 = _make_binary_msg(GCOV_MSG_FULL, SAT, 0, 100, full_grids_0)
        assert process_binary_message(msg0, self.analyzer)
        assert len(_binary_state[str(SAT)]) == 20

        # t=1: Delta — add 3, remove 2
        add_1 = [2000, 2001, 2002]
        rm_1 = [1000, 1001]
        msg1 = _make_binary_msg(GCOV_MSG_DELTA, SAT, 1, 101, add_1, rm_1)
        assert process_binary_message(msg1, self.analyzer)
        state1 = _binary_state[str(SAT)]
        assert len(state1) == 21  # 20 - 2 + 3
        assert 2000 in state1 and 1000 not in state1

        # t=2: Delta — add 1, remove 5
        add_2 = [3000]
        rm_2 = [1002, 1003, 1004, 1005, 1006]
        msg2 = _make_binary_msg(GCOV_MSG_DELTA, SAT, 2, 102, add_2, rm_2)
        assert process_binary_message(msg2, self.analyzer)
        state2 = _binary_state[str(SAT)]
        assert len(state2) == 17  # 21 - 5 + 1
        assert 3000 in state2

        # t=3: Full resync with 15 grids
        full_grids_3 = list(range(5000, 5015))
        msg3 = _make_binary_msg(GCOV_MSG_FULL, SAT, 3, 103, full_grids_3)
        assert process_binary_message(msg3, self.analyzer)
        state3 = _binary_state[str(SAT)]
        assert len(state3) == 15
        assert state3 == set(full_grids_3)

        # Analyzer should have recorded messages
        assert self.analyzer.total_messages == 4
        assert str(SAT) in self.analyzer.unique_sats

# ===========================================================================
# Test 3: Terminal Location Lifecycle
# ===========================================================================

class TestTerminalLocationLifecycle:
    """Register, move, handover, keepalive, expire, and export terminals."""

    def setup_method(self):
        self.mgr = TerminalLocationManager(
            keepalive_timeout=0.5, handover_threshold=0.0
        )

    def test_lifecycle(self):
        grids = ["F00_0", "F00_1", "F00_2"]

        # Step 1: register 10 terminals across 3 grids
        for i in range(10):
            grid = grids[i % 3]
            sat = (i % 3) + 1
            assert self.mgr.register(f"T{i}", grid, sat)

        assert len(self.mgr.terminals) == 10
        assert self.mgr.stats["registrations"] == 10

        # Step 2: set up coverage for each grid
        for idx, g in enumerate(grids):
            self.mgr.update_grid_coverage(g, [
                (1, 100 - idx * 10),
                (2, 90 - idx * 10),
                (3, 80 - idx * 10),
            ])

        # Step 3: move 5 terminals to new grids
        for i in range(5):
            old_grid = grids[i % 3]
            new_grid = grids[(i + 1) % 3]
            new_sat = ((i + 1) % 3) + 1
            self.mgr.update_location(f"T{i}", new_grid, new_sat)

        # Step 4: verify handover counts
        assert self.mgr.stats["handovers"] == 5

        # Step 5: resolve coverage conflicts
        for tid in list(self.mgr.terminals):
            rec = self.mgr.terminals[tid]
            best = self.mgr.resolve_coverage_conflict(rec.grid_code, tid)
            assert best is not None

        # Step 6: keepalive some, let others expire
        for i in range(5):
            self.mgr.keepalive(f"T{i}")

        # Force expiration by manipulating keepalive timestamps
        now = time.time()
        for i in range(5, 10):
            tid = f"T{i}"
            if tid in self.mgr.terminals:
                self.mgr.terminals[tid].last_keepalive = now - 10.0

        expired = self.mgr.expire_stale()
        assert len(expired) == 5

        # Step 7: verify grid index consistency
        for tid, rec in self.mgr.terminals.items():
            assert tid in self.mgr.grid_terminals[rec.grid_code]

        # Step 8: export and verify JSON structure
        export_path = tempfile.mktemp(suffix=".json")
        try:
            self.mgr.export_state(export_path)
            data = json.loads(Path(export_path).read_text())
            assert "timestamp" in data
            assert "statistics" in data
            assert "terminals" in data
            assert data["statistics"]["active_terminals"] == 5
        finally:
            if os.path.exists(export_path):
                os.unlink(export_path)

# ===========================================================================
# Test 4: FRR-to-P4 Sync Pipeline
# ===========================================================================

class TestFRRToP4SyncPipeline:
    """Parse vtysh output, convert to P4 entries, validate format."""

    VTYSH_ROUTES = """\
Codes: K - kernel route, C - connected, S - static, R - RIP,
       O - OSPF, I - IS-IS, B - BGP, E - EIGRP, N - NHRP,
       T - Table, v - VNC, V - VNC-Direct, A - Babel, F - PBR,
       f - OpenFabric, t - Table-Direct,
       > - selected route, * - FIB route, q - queued, r - rejected, b - backup
       t - trapped, o - offload failure

I>* 10.0.1.0/24 [115/20] via 10.0.12.2, eth-r1r2, weight 1, 00:01:00
I>* 10.0.2.0/24 [115/30] via 10.0.13.3, eth-r1r3, weight 1, 00:01:00
I>* 10.0.3.0/24 [115/40] via 10.0.14.4, eth-r1r4, weight 1, 00:01:00
I   10.0.5.0/24 [115/50] via 10.0.15.5, eth-r1r5, weight 1, 00:01:00
"""

    VTYSH_DB = """\
IS-IS Level-2 link-state database:
LSP ID                  PduLen  SeqNumber   Chksum  Holdtime  ATT/P/OL
r1.00-00             *    200  0x00000005  0xabcd    1100    0/0/0
  LCSA: sat=1 state=current prio=100 dur=60 ts=1700000000 grids=20
  LCSA: sat=2 state=current prio=90 dur=45 ts=1700000001 grids=15
  LCSA: sat=3 state=predicted prio=50 dur=30 ts=1700000002 grids=10
"""

    def test_parse_routes_and_convert(self):
        routes = parse_isis_routes(self.VTYSH_ROUTES)
        assert len(routes) == 4
        assert routes[0].prefix == "10.0.1.0/24"
        assert routes[0].nexthop == "10.0.12.2"

        p4 = routes_to_p4_entries(routes)
        assert len(p4) == 4
        for entry in p4:
            cmd = entry.to_cli_command()
            assert cmd.startswith("table_add MyIngress.ipv4_lpm")
            assert "=>" in cmd

    def test_parse_lcsa_and_convert(self):
        lcsa = parse_isis_database_lcsa(self.VTYSH_DB)
        assert len(lcsa) == 3
        assert lcsa[0]["satellite_id"] == 1
        assert lcsa[2]["state"] == "predicted"

        p4 = lcsa_to_p4_entries(lcsa)
        assert len(p4) == 3
        for entry in p4:
            cmd = entry.to_cli_command()
            assert "satellite_forwarding" in cmd

    def test_no_duplicate_entries(self):
        routes = parse_isis_routes(self.VTYSH_ROUTES)
        lcsa = parse_isis_database_lcsa(self.VTYSH_DB)
        all_entries = routes_to_p4_entries(routes) + lcsa_to_p4_entries(lcsa)
        cmds = [e.to_cli_command() for e in all_entries]
        assert len(cmds) == len(set(cmds)), "Duplicate P4 entries detected"

    def test_empty_input(self):
        assert parse_isis_routes("") == []
        assert parse_isis_routes("no routes here\n") == []
        assert parse_isis_database_lcsa("") == []
        assert routes_to_p4_entries([]) == []
        assert lcsa_to_p4_entries([]) == []

    def test_prefix_to_lpm_format(self):
        assert prefix_to_lpm("10.0.1.0/24") == "0x0a000100/24"

    def test_ip_to_mac_format(self):
        assert ip_to_mac("10.0.12.2") == "00:00:0a:00:0c:02"

# ===========================================================================
# Test 5: Coverage Change Detection Simulation
# ===========================================================================

class TestCoverageChangeDetection:
    """Detect changes in coverage files across reads."""

    def setup_method(self):
        self.tmpdir = Path(tempfile.mkdtemp(prefix="cov-change-"))
        self.injector = CoverageInjector(
            state_dir=self.tmpdir, throttle_interval=0.0
        )

    def teardown_method(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _read_all(self):
        """Read all sat files and return {sat_id: data_dict}."""
        result = {}
        for f in sorted(self.tmpdir.glob("sat_*.json")):
            data = json.loads(f.read_text())
            result[data["satellite_id"]] = data
        return result

    def test_change_detection(self):
        # Step 1: create initial coverage for 3 satellites
        initial = {
            "1": (["F00_0", "F00_1", "F00_2"], 1000.0),
            "2": (["F01_0", "F01_1"], 1000.0),
            "3": (["F02_0"], 1000.0),
        }
        for sid, (grids, ts) in initial.items():
            self.injector.inject_coverage(sid, grids, timestamp=ts)

        # Step 2: read and record state
        state_v1 = self._read_all()
        assert len(state_v1) == 3

        # Step 3: modify sat 1 coverage (change grids AND timestamp)
        self.injector.inject_coverage("1", ["F00_5", "F00_6"], timestamp=2000.0)
        state_v2 = self._read_all()
        assert state_v2["1"]["grid_codes"] != state_v1["1"]["grid_codes"]
        assert state_v2["1"]["timestamp"] != state_v1["1"]["timestamp"]
        # sat 2 and 3 unchanged
        assert state_v2["2"] == state_v1["2"]
        assert state_v2["3"] == state_v1["3"]

        # Step 5: modify sat 2 timestamp only (same grids)
        self.injector.inject_coverage("2", ["F01_0", "F01_1"], timestamp=3000.0)
        state_v3 = self._read_all()
        assert state_v3["2"]["grid_codes"] == state_v1["2"]["grid_codes"]
        assert state_v3["2"]["timestamp"] != state_v1["2"]["timestamp"]

        # Step 7: re-read without changes — verify no change
        state_v4 = self._read_all()
        assert state_v4 == state_v3

# ===========================================================================
# Test 6: Stress Test
# ===========================================================================

class TestStress:
    """High-volume operations: 100 terminals, 20 satellites, 50 grids each."""

    def setup_method(self):
        self.tmpdir = Path(tempfile.mkdtemp(prefix="cov-stress-"))
        self.injector = CoverageInjector(
            state_dir=self.tmpdir, throttle_interval=0.0
        )
        self.mgr = TerminalLocationManager(
            keepalive_timeout=9999.0, handover_threshold=0.0
        )

    def teardown_method(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_stress(self):
        NUM_TERMINALS = 100
        NUM_SATS = 20
        GRIDS_PER_SAT = 50
        MOVES_PER_TERMINAL = 5

        # Step 1: register 100 terminals
        all_grids = [f"F{s:02d}_{g}" for s in range(NUM_SATS)
                     for g in range(GRIDS_PER_SAT)]
        for i in range(NUM_TERMINALS):
            grid = all_grids[i % len(all_grids)]
            sat = (i % NUM_SATS) + 1
            self.mgr.register(f"T{i}", grid, sat)

        assert len(self.mgr.terminals) == NUM_TERMINALS

        # Step 2: inject coverage for 20 satellites with 50 grids each
        for s in range(NUM_SATS):
            sat_id = str(s + 1)
            grids = [f"F{s:02d}_{g}" for g in range(GRIDS_PER_SAT)]
            ok = self.injector.inject_coverage(sat_id, grids)
            assert ok

        assert self.injector.inject_count == NUM_SATS

        # Step 3: move all terminals through 5 position updates
        for move in range(MOVES_PER_TERMINAL):
            for i in range(NUM_TERMINALS):
                idx = (i + move + 1) % len(all_grids)
                new_grid = all_grids[idx]
                new_sat = (idx // GRIDS_PER_SAT) + 1
                self.mgr.update_location(f"T{i}", new_grid, new_sat)

        # Step 4: verify no crashes, check object counts
        assert len(self.mgr.terminals) == NUM_TERMINALS
        stats = self.mgr.get_statistics()
        assert stats["active_terminals"] == NUM_TERMINALS
        assert stats["registrations"] == NUM_TERMINALS

        # Step 5: verify statistics consistency
        # Total updates = moves that actually changed location
        # (some moves may land on the same grid/sat, so updates <= total moves)
        assert stats["updates"] <= NUM_TERMINALS * MOVES_PER_TERMINAL
        assert stats["handovers"] <= NUM_TERMINALS * MOVES_PER_TERMINAL
        assert stats["handovers"] == stats["updates"]  # every real update is a handover

        # Grid index consistency
        for tid, rec in self.mgr.terminals.items():
            assert tid in self.mgr.grid_terminals[rec.grid_code], \
                f"Terminal {tid} not in grid index for {rec.grid_code}"

        # Injector stats
        inj_stats = self.injector.get_statistics()
        assert inj_stats["inject_count"] == NUM_SATS
        assert inj_stats["error_count"] == 0
