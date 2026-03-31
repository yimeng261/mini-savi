import unittest
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from control_plane_utils import compute_link_state_updates
from receive_grid_coverage_data import GridCoverageAnalyzer, GridType, process_coverage_message


class ProtocolAndLinkTests(unittest.TestCase):
    def test_fragmented_coverage_messages_merge_once(self):
        analyzer = GridCoverageAnalyzer()
        pending = {}

        self.assertFalse(process_coverage_message("1@1/2:F00_0,F00_1", analyzer, pending))
        self.assertEqual(analyzer.total_messages, 0)

        self.assertTrue(process_coverage_message("1@2/2:F00_2,F00_3", analyzer, pending))
        self.assertEqual(analyzer.total_messages, 1)
        self.assertEqual(analyzer.satellite_message_count["1"], 1)
        self.assertIn("F00_3", analyzer.unique_grids[GridType.ICOSAHEDRAL])

    def test_compute_link_state_updates_only_returns_changes(self):
        isls_origin = {
            0: {2: object(), 1: object()},
            1: {3: object()},
            2: {0: object()},
        }
        isl_delays = {
            0: {2: 0.1, 1: 0.0},
            1: {3: 0.0},
            2: {0: 0.1},
        }
        previous = {(0, 2): "down"}

        updates, next_states = compute_link_state_updates(
            isls_origin, isl_delays, sats_per_plane=2, link_states=previous
        )

        self.assertEqual(updates, [(0, 2, "up"), (1, 3, "down")])
        self.assertEqual(next_states[(0, 2)], "up")
        self.assertEqual(next_states[(1, 3)], "down")
