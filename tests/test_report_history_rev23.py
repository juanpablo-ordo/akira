from datetime import datetime, timezone
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from operation_report import build_report, read_recent_events


class ReportHistoryTests(unittest.TestCase):
    def test_closed_market_keeps_risk_closures_and_decisions_in_period(self):
        now = 1794712159
        exit_time = now - 2400
        placed = datetime.fromtimestamp(exit_time - 600, timezone.utc).isoformat()
        snapshot = {
            'as_of_utc': now,
            'repair_id': 'Revisión 23',
            'symbols': {'XAUUSDm': {}},
            'markets': {'XAUUSDm': {'scheduled_closed': True}},
            'orders': [{'symbol': 'XAUUSDm', 'ticket': 56, 'type': 3, 'entry': 2100, 'sl': 2120, 'tp': 2050}],
            'portfolio_risk': {'reserved_usd': 2, 'rows': [
                {'symbol': 'XAUUSDm', 'ticket': 56, 'kind': 'pending', 'reserved_usd': 2},
            ]},
            'history_deals': [
                {'position_id': 42, 'symbol': 'XAUUSDm', 'time': exit_time - 900,
                 'type': 1, 'entry': 0, 'price': 2100, 'volume': 0.01, 'magic': 170002},
                {'position_id': 42, 'symbol': 'XAUUSDm', 'time': exit_time,
                 'type': 0, 'entry': 1, 'price': 2080, 'volume': 0.01, 'profit': 20, 'commission': -1},
            ],
            'operational_events': [
                {'utc': placed, 'symbol': 'XAUUSDm', 'operation': 'cancel', 'reason': 'Venció'},
            ],
        }
        result = build_report(snapshot, 24)
        self.assertEqual(result['repair_id'], 'Revisión 23')
        self.assertEqual([(r['side'], r['net_usd']) for r in result['closed']], [('SELL', 19)])
        self.assertEqual(result['tables']['Cierres'][0][1], 'XAUUSDm')
        self.assertEqual(result['tables']['Decisiones'][0][4], 'Venció')
        self.assertEqual(result['pendings'], [])
        self.assertEqual(result['snapshot']['portfolio_risk']['reserved_usd'], 2)
        self.assertEqual(result['tables']['Riesgo'][0][:2], ['56', 'XAUUSDm'])
        self.assertEqual(build_report(snapshot, 0)['closed'], [])

    def test_sampled_decisions_are_read_separately_and_scoped_to_account(self):
        now = datetime(2026, 11, 14, 18, tzinfo=timezone.utc)
        row = {
            'utc': now.isoformat(), 'symbol': 'BTCUSDm', 'operation': 'pending_decision',
            'pending_decision_scope': 'current',
            'pending_decisions': {'scenarios': [
                {'direction': 'SELL STOP', 'state': 'NO ENVIADA', 'rejection_counts': {'distance': 3}},
            ]},
        }
        other = {**row, 'pending_decision_scope': 'other'}
        with TemporaryDirectory() as directory:
            folder = Path(directory)
            (folder / 'eventos_2026-11-14.jsonl').write_text('x' * 2048, encoding='utf-8')
            (folder / 'decisiones_2026-11-14.jsonl').write_text(
                '\n'.join(json.dumps(item) for item in (row, other)), encoding='utf-8')
            events, truncated = read_recent_events(folder, 24, now.timestamp(), max_bytes=1024)
        self.assertTrue(truncated)
        self.assertEqual(len(events), 2)
        result = build_report({
            'as_of_utc': now.timestamp(), 'operational_events': events,
            'pending_decision_scope': 'current',
        })
        summaries = [item for item in result['tables']['Resumen'] if item[0] == 'Decisión']
        self.assertEqual(summaries[0][1:3], ['BTCUSDm SELL STOP', 1])
        self.assertIn('distance: 1', summaries[0][3])
        self.assertEqual(result['snapshot']['operational_events'], [row])
