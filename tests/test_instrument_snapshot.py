import sys
import types
import unittest
from unittest.mock import patch

from app.providers.instrument_provider import _futu_cn_snapshot


class _Frame:
    empty = False

    class _Row:
        def to_dict(self):
            return {'name':'比亚迪','last_price':82.53,'update_time':'2026-10-27 11:30:00',
                    'equity_valid':True,'pe_ratio':23.065,'pe_ttm_ratio':25.566,'pb_ratio':3.135}

    class _ILoc:
        def __getitem__(self, index):
            assert index == 0
            return _Frame._Row()

    iloc = _ILoc()


class InstrumentSnapshotTests(unittest.TestCase):
    def test_futu_valuation_keeps_source_pe_labels(self):
        class Context:
            def __init__(self, **kwargs):
                pass

            def get_market_snapshot(self, codes):
                self.assert_codes(codes)
                return 0, _Frame()

            @staticmethod
            def assert_codes(codes):
                assert codes == ['SZ.002594']

            def close(self):
                pass

        fake = types.SimpleNamespace(OpenQuoteContext=Context, RET_OK=0)
        with patch.dict(sys.modules, {'futu': fake}), \
             patch('app.providers.futu_provider.address', return_value=('127.0.0.1', 11111)):
            result = _futu_cn_snapshot('002594')
        rows = {item['item']:item['value'] for item in result['rows']}
        self.assertEqual(rows['市盈率（富途口径）'], 23.065)
        self.assertEqual(rows['市盈率（TTM）'], 25.566)
        self.assertEqual(rows['市净率'], 3.135)
        self.assertNotIn('市盈率（动）', rows)
        self.assertEqual(result['source_time'], '2026-10-27T03:30:00+00:00')


if __name__ == '__main__':
    unittest.main()
