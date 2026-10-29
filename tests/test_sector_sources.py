import sys
import types
import unittest
from unittest.mock import patch

from app.market_context import _ths_rotation_rows
from app.providers.sector_provider import _fetch_source


class SectorSourceTests(unittest.TestCase):
    def test_ths_rotation_keeps_fund_flow_separate_from_main_flow(self):
        rows = _ths_rotation_rows([{"行业": "汽车整车", "阶段涨跌幅": "-1.25%", "净额": -2.5}], "5日")
        self.assertEqual(rows[0]["5日涨跌幅"], -1.25)
        self.assertEqual(rows[0]["资金净额-元"], -250_000_000)
        self.assertNotIn("主力净流入-净额", rows[0])

    def test_sector_catalog_and_flow_fall_back_to_ths(self):
        class Frame:
            empty = False

            def __init__(self, rows):
                self.rows = rows

            def to_dict(self, orient):
                self.assert_orient(orient)
                return self.rows

            @staticmethod
            def assert_orient(orient):
                assert orient == "records"

        def unavailable(*args, **kwargs):
            raise ConnectionError("push2 unavailable")

        fake = types.SimpleNamespace(
            stock_board_industry_name_em=unavailable,
            stock_board_industry_summary_ths=lambda: Frame([{"板块": "汽车整车", "涨跌幅": 1.2}]),
            stock_sector_fund_flow_rank=unavailable,
            stock_fund_flow_industry=lambda symbol: Frame([{"行业": "汽车整车", "净额": 1.25}]),
        )
        with patch.dict(sys.modules, {"akshare": fake}):
            catalog = _fetch_source("sectors", None)
            flow = _fetch_source("flow", "汽车整车")
        self.assertEqual(catalog[0]["板块名称"], "汽车整车")
        self.assertEqual(catalog[0]["_source"], "同花顺")
        self.assertEqual(flow[0]["资金净额-元"], 125_000_000)
        self.assertEqual(flow[0]["_source"], "同花顺")


if __name__ == "__main__":
    unittest.main()
