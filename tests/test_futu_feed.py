from __future__ import annotations

import unittest

from app.index_feed import IndexFeed
from app.mysql_db import _translate
from app.providers.futu_provider import code_for, normalize_snapshot


class FutuFeedContractTest(unittest.TestCase):
    def test_market_codes_and_nav_exclusion(self):
        self.assertEqual(code_for('CN:600519'), 'SH.600519')
        self.assertEqual(code_for('CN:300750'), 'SZ.300750')
        self.assertEqual(code_for('FUND:510050'), 'SH.510050')
        self.assertIsNone(code_for('FUND:000001'))
        self.assertEqual(code_for('HK:700'), 'HK.00700')
        self.assertEqual(code_for('US:AAPL'), 'US.AAPL')

    def test_snapshot_keeps_exchange_time_and_source(self):
        raw = {'code': 'HK.00700', 'name': '腾讯控股', 'last_price': 600,
               'prev_close_price': 590, 'update_time': '2026-10-26 10:30:00'}
        kind, row = normalize_snapshot(raw, 'HK:00700')
        self.assertEqual(kind, 'quote')
        self.assertEqual(row['quote_kind'], 'snapshot')
        self.assertEqual(row['known_delay_seconds'], None)
        self.assertIn('02:30:00', row['exchange_time'])
        self.assertIn('快照', row['provider'])

    def test_push_is_distinct_from_snapshot(self):
        raw = {'code': 'SH.000001', 'last_price': 4000, 'prev_close_price': 3990,
               'data_date': '2026-10-26', 'data_time': '10:30:01'}
        kind, row = normalize_snapshot(raw, pushed=True)
        self.assertEqual(kind, 'index')
        self.assertEqual(row['id'], 'INDEX:SH000001')
        self.assertEqual(row['feed'], 'push')
        self.assertIn('02:30:01', row['source_time'])

    def test_old_snapshot_cannot_replace_new_push(self):
        feed = IndexFeed()
        pushed = normalize_snapshot({'code': 'SH.000001', 'last_price': 4000,
            'data_date': '2026-10-26', 'data_time': '10:30:01'}, pushed=True)[1]
        older = normalize_snapshot({'code': 'SH.000001', 'last_price': 3990,
            'update_time': '2026-10-26 10:30:00'})[1]
        feed.ingest_futu([pushed, older])
        self.assertEqual(feed._observations['INDEX:SH000001']['futu']['last'], 4000)

    def test_untimed_scrape_cannot_displace_futu_exchange_time(self):
        feed = IndexFeed()
        futu = normalize_snapshot({'code': 'SH.000001', 'last_price': 4000,
            'update_time': '2026-10-26 10:30:00'})[1]
        feed.ingest_futu([futu])
        scrape = {**futu, 'last': 3990, 'source_time': None}
        feed._apply('akshare', [scrape])
        selected = next(row for row in feed.snapshot()['indices'] if row['id'] == futu['id'])
        self.assertEqual(selected['last'], 4000)

    def test_mysql_adapter_preserves_literal_like_percent(self):
        sql = _translate("SELECT instrument_id FROM quotes WHERE provider LIKE '富途 OpenD%' AND received_at>=?")
        self.assertIn("LIKE '富途 OpenD%%'", sql)
        self.assertIn('received_at>=%s', sql)


if __name__ == '__main__':
    unittest.main()
