from __future__ import annotations

import ast
import importlib.util
from pathlib import Path
import sys
import unittest

from graham_research.legacy import assess_graham_snapshot
from graham_research.live import get_live_app


class LiveIntegrationTests(unittest.TestCase):
    def test_facade_is_lazy(self) -> None:
        self.assertNotIn("graham_research.live_app", sys.modules)
        self.assertTrue(callable(get_live_app))

    def test_full_api_is_packaged_and_marked_live_only(self) -> None:
        spec = importlib.util.find_spec("graham_research.live_app")
        self.assertIsNotNone(spec)
        source = Path(spec.origin).read_text(encoding="utf-8")
        tree = ast.parse(source)
        function_names = {
            node.name
            for node in ast.walk(tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        }
        self.assertIn("analyze_company", function_names)
        self.assertIn("create_thesis", function_names)
        self.assertIn("diff_thesis", function_names)
        self.assertIn("HISTORICAL_BACKTEST_ELIGIBLE = False", source)
        self.assertIn('"historical_backtest_eligible": False', source)

    def test_live_output_boundary_remains_closed(self) -> None:
        result = assess_graham_snapshot({
            "company": {"ticker": "AAA"},
            "metrics": {"normalized_eps": 2.0},
            "research_eligibility": {
                "scope": "live_analysis_only",
                "historical_backtest_eligible": False,
            },
        })
        self.assertTrue(result.reusable_for_live_research)
        self.assertFalse(result.eligible_for_historical_backtest)


if __name__ == "__main__":
    unittest.main()
