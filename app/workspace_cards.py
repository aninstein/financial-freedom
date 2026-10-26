"""UI navigation is derived from actual tool evidence, never from model-authored URLs."""
from __future__ import annotations
from typing import Any


def build_research_cards(evidence: list[dict[str, Any]]) -> list[dict[str, Any]]:
    cards: dict[str, dict[str, Any]] = {}
    for item in evidence:
        detail = item.get('detail') or {}
        kind = item.get('type')
        instrument = detail.get('instrument_id')
        if kind == 'financial_data' and detail.get('symbol'):
            instrument = 'CN:' + detail['symbol']
        elif kind in {'fund_holdings', 'fund_trade_disclosure'} and detail.get('fund_code'):
            instrument = 'FUND:' + detail['fund_code']
        if kind in {'market_news','macro_liquidity','sector_rotation'}:
            cards[kind]={'kind':'context','context':kind,'title':item.get('title'),'evidence_ids':[item.get('evidence_id')]}
            continue
        if kind == 'index_analysis':
            index_id=detail.get('id')
            if index_id:
                cards['index:'+index_id]={'kind':'index','instrument_id':index_id,'name':detail.get('name'),
                    'last_close':detail.get('analysis',{}).get('latest_close'),'last_bar':detail.get('analysis',{}).get('last_bar'),
                    'state':detail.get('state'),'evidence_ids':[item.get('evidence_id')]}
            continue
        if kind == 'historical_cycles' and instrument:
            cards['cycles:'+instrument]={'kind':'cycles','instrument_id':instrument,'last_bar':detail.get('last_bar'),
                                        'evidence_ids':[item.get('evidence_id')]}
            continue
        if instrument and kind in {'quote', 'daily_research', 'backtest', 'financial_data', 'fund_holdings', 'fund_trade_disclosure', 'stock_dossier'}:
            key = 'instrument:' + instrument
            card = cards.setdefault(key, {'kind': 'instrument', 'instrument_id': instrument,
                                         'name': detail.get('name') or instrument, 'evidence_ids': []})
            card['evidence_ids'].append(item.get('evidence_id'))
            card.update({k: detail[k] for k in ('last', 'currency', 'change_percent', 'freshness', 'sma_20', 'sma_50', 'name') if k in detail})
            if kind == 'quote':
                card.update({k: detail[k] for k in ('provider', 'quote_kind', 'known_delay_seconds', 'exchange_time', 'received_at') if k in detail})
                card['source'] = item.get('source')
                card['as_of'] = item.get('as_of')
        elif kind == 'market_snapshot' and detail.get('market'):
            cards['market:' + detail['market']] = {'kind': 'market', **detail, 'evidence_ids': [item.get('evidence_id')]}
        elif kind == 'sector_snapshot' and detail.get('name'):
            cards['sector:' + detail['name']] = {'kind': 'sector', 'name': detail['name'], 'market': 'CN',
                                                'summary': detail.get('summary'), 'flow': detail.get('flow'),
                                                'state': detail.get('state'), 'evidence_ids': [item.get('evidence_id')]}
        elif kind == 'fund_screen':
            for row in detail.get('rows', [])[:6]:
                instrument = row.get('instrument_id')
                if instrument:
                    cards.setdefault('instrument:' + instrument, {'kind': 'instrument', **row,
                                                                  'evidence_ids': [item.get('evidence_id')]})
    return list(cards.values())[:12]
