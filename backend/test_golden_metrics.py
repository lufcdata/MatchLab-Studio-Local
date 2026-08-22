from __future__ import annotations

import unittest
from pathlib import Path

from golden_metrics import METRICS, format_metric_value, metric_key, player_metric_value


ROOT = Path(__file__).resolve().parents[1]
APP_TSX = ROOT / "frontend" / "src" / "App.tsx"


class GoldenMetricAuditTests(unittest.TestCase):
    def metric(self, label: str):
        return next(m for m in METRICS if m["label"] == label)

    def test_metric_labels_and_keys_are_unique(self):
        labels = [m["label"] for m in METRICS]
        keys = [metric_key(label) for label in labels]
        self.assertEqual(len(labels), len(set(labels)), "Duplicate Golden metric label")
        self.assertEqual(len(keys), len(set(keys)), "Duplicate Golden metric key")

    def test_every_player_metric_has_source_or_calculation(self):
        for metric in METRICS:
            if metric.get("player_keys"):
                self.assertTrue(metric.get("player_keys") or metric.get("calculated"), f"{metric['label']} has no player source")

    def test_frontend_uses_runtime_golden_catalogue_only(self):
        source = APP_TSX.read_text()
        self.assertIn("/canonical/metrics", source)
        self.assertNotIn("const MATCH_FIELDS", source)
        self.assertNotIn("const REQUIRED_LEADER_FIELDS", source)

    def test_big_chance_zero_fallback_requires_participation(self):
        played = {"minutesPlayed": 90, "touches": 42}
        unused = {}
        for label in ("Big Chances", "Big Chances Created", "Big Chances Missed"):
            metric = self.metric(label)
            self.assertEqual(player_metric_value(played, metric), 0.0)
            self.assertIsNone(player_metric_value(unused, metric))

    def test_player_big_chances_are_scored_plus_missed_not_created(self):
        metric = self.metric("Big Chances")
        stats = {"minutesPlayed": 90, "bigChanceScored": 2, "bigChanceMissed": 1, "bigChanceCreated": 5}
        self.assertEqual(player_metric_value(stats, metric), 3.0)

    def test_tackles_won_never_falls_back_to_total_tackles(self):
        metric = self.metric("Tackles Won")
        self.assertEqual(player_metric_value({"minutesPlayed": 90, "wonTackle": 2, "totalTackle": 5}, metric), 2.0)
        self.assertIsNone(player_metric_value({"minutesPlayed": 90, "totalTackle": 5}, metric))

    def test_ground_duels_won_prefers_direct_then_derives_from_all_minus_aerial(self):
        metric = self.metric("Ground Duels Won")
        self.assertEqual(player_metric_value({"groundDuelWon": 6, "duelWon": 10, "aerialWon": 3}, metric), 6.0)
        self.assertEqual(player_metric_value({"duelWon": 10, "aerialWon": 3}, metric), 7.0)
        self.assertEqual(player_metric_value({"duelWon": 4}, metric), 4.0)
        self.assertEqual(player_metric_value({"duelWon": 2, "aerialWon": 3}, metric), 0.0)
        self.assertIsNone(player_metric_value({}, metric))

    def test_penalties_won_and_red_cards_zero_fallback_requires_participation(self):
        played = {"minutesPlayed": 90, "touches": 42}
        unused = {}
        for label in ("Penalties Won", "Red Cards"):
            metric = self.metric(label)
            self.assertEqual(player_metric_value(played, metric), 0.0)
            self.assertIsNone(player_metric_value(unused, metric))

    def test_high_claims_zero_is_goalkeeper_only(self):
        metric = self.metric("High Claims")
        goalkeeper = {"minutesPlayed": 90, "saves": 3}
        outfield = {"minutesPlayed": 90, "touches": 55}
        unused_goalkeeper_shape = {"saves": None}
        self.assertEqual(player_metric_value(goalkeeper, metric), 0.0)
        self.assertIsNone(player_metric_value(outfield, metric))
        self.assertIsNone(player_metric_value(unused_goalkeeper_shape, metric))

    def test_defensive_actions_matches_golden_formula(self):
        metric = self.metric("Defensive Actions")
        stats = {"totalTackle": 2, "interceptionWon": 1, "blockedScoringAttempt": 1, "totalClearance": 4, "ballRecovery": 5, "aerialWon": 3, "fouls": 2}
        self.assertEqual(player_metric_value(stats, metric), 18.0)
        self.assertIsNone(player_metric_value({}, metric))

    def test_pass_accuracy_derives_from_pass_counts(self):
        metric = self.metric("Pass Accuracy")
        self.assertAlmostEqual(player_metric_value({"accuratePass": 37, "totalPass": 41}, metric), 37 / 41 * 100)
        self.assertIsNone(player_metric_value({"accuratePass": 0, "totalPass": 0}, metric))

    def test_shared_number_formatting(self):
        self.assertEqual(format_metric_value(1.234, self.metric("xG")), "1.23")
        self.assertEqual(format_metric_value(72.0, self.metric("Pass Accuracy")), "72%")
        self.assertEqual(format_metric_value(72.4, self.metric("Pass Accuracy")), "72.4%")
        self.assertEqual(format_metric_value(12.0, self.metric("Touches")), "12")


if __name__ == "__main__":
    unittest.main()
