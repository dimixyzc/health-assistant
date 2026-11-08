import asyncio
import importlib.util
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch


# The report runner lives outside the separately built add-on, so load its
# owning source explicitly when checking either runtime context.
spec = importlib.util.spec_from_file_location("report_under_test", Path(__file__).resolve().parents[1] / "health_report.py")
report = importlib.util.module_from_spec(spec)
spec.loader.exec_module(report)


class ReportContextTest(unittest.TestCase):
    def test_missing_fields_are_omitted_but_zero_and_false_survive(self):
        self.assertEqual(report._compact({"steps": 0, "available": False, "hrv": None, "empty": {}, "list": [], "nested": {"value": None}}),
                         {"steps": 0, "available": False})

    def test_long_term_values_sent_once_and_daily_changes_preserved(self):
        snapshot = {"date": "2026-11-08", "steps": 0, "avg_hrv": None,
                    "long_term_metrics": {"vo2_max": 45},
                    "long_term_changes": {"vo2_max": {"delta": 1}}}
        config = SimpleNamespace(data_dir="/unused", knowledge_book_path="", knee_rehab_active=True)
        with patch.object(report, "settings", config), \
             patch.object(report.db, "init_db", AsyncMock()), \
             patch.object(report.db, "get_active_experiments", AsyncMock(return_value=[])), \
             patch.object(report.insights, "refresh_renpho_cache", AsyncMock()), \
             patch.object(report.insights, "get_weight_trend", AsyncMock(return_value={"available": False})), \
             patch.object(report.insights, "get_training_plan", AsyncMock(return_value={"snapshot": snapshot, "weekly": {"long_term_metrics": {"vo2_max": 45}}})), \
             patch.object(report, "KnowledgeBase") as knowledge:
            knowledge.return_value.context.return_value = {"book_available": False}
            result = asyncio.run(report.build_report("morning"))
        self.assertNotIn("long_term_metrics", result["daily_snapshot"])
        self.assertIn("long_term_changes", result["daily_snapshot"])
        self.assertEqual(result["week_context"]["long_term_metrics"], {"vo2_max": 45})
        self.assertEqual(result["daily_snapshot"]["steps"], 0)
        self.assertNotIn("avg_hrv", result["daily_snapshot"])
