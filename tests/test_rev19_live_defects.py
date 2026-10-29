"""Regressions from live REV18 evidence on 29 October 2026.

These tests never touch a live MT5 terminal or place orders.
"""
import copy
import unittest
from datetime import datetime, timezone
from market_calendar import xau_state
from operation_health import execution_gate
from user_locale import local_now, format_local, selected_timezone, validate_timezone
from settings import DEFAULT, load_config
from entry_safety import loss_pause
from source_recovery import SourceDeadline


class LiveDefectsRev19(unittest.TestCase):
    def test_xau_thursday_after_rollover_is_scheduled_open(self):
        at = datetime(2026, 10, 29, 22, 36, tzinfo=timezone.utc)
        self.assertTrue(xau_state(at).open)

    def test_risk_cooldown_is_not_broker_error(self):
        gate = execution_gate('trade', runtime_block=(
            'Pausa de nuevas entradas: 3 pérdidas propias consecutivas confirmadas'))
        self.assertEqual(gate['code'], 'RISK_COOLDOWN')
        self.assertFalse(gate['execution_allowed'])
        self.assertEqual(execution_gate('trade', runtime_block='No autorizado por MT5')['code'], 'BROKER_BLOCK')

    def test_user_can_disable_only_loss_circuit(self):
        cfg = load_config(DEFAULT)
        cfg['capital_protection']['loss_streak_enabled'] = False
        rows = [
            {'position_id': i, 'closed_at': 1800000000-i*20, 'pnl': -1,
             'deal_ids': [2*i, 2*i+1]} for i in range(1, 4)
        ]
        status = loss_pause(cfg, rows, 1800000000)
        self.assertTrue(status['allowed'])
        self.assertFalse(status['enabled'])
        self.assertTrue(cfg['capital_protection']['enabled'])
        cfg['capital_protection']['loss_streak_enabled'] = True
        self.assertFalse(loss_pause(cfg, rows, 1800000000)['allowed'])

    def test_youtube_is_not_automatic_even_for_old_saved_profile(self):
        old = copy.deepcopy(DEFAULT)
        old['assistant']['auto_youtube_research'] = True
        old['research']['youtube'] = True
        cfg = load_config(old)
        self.assertFalse(cfg['assistant']['auto_youtube_research'])
        self.assertFalse(cfg['research']['youtube'])

    def test_timezone_comes_from_selected_region(self):
        cfg = load_config(DEFAULT)
        self.assertEqual(selected_timezone(cfg), 'America/Guatemala')
        utc = datetime(2026, 10, 29, 22, 36, tzinfo=timezone.utc)
        self.assertIn('16:36', format_local(utc, cfg))
        cfg['locale'].update(country='Estados Unidos', region='Nueva York', timezone='America/New_York')
        self.assertIn('18:36', format_local(utc, cfg))
        self.assertEqual(local_now(cfg).tzinfo.key, 'America/New_York')

    def test_dns_failure_does_not_spin_across_query_variants(self):
        source = SourceDeadline()
        calls = []
        def failed():
            calls.append('attempt')
            raise OSError('[Errno 11002] getaddrinfo failed')
        with self.assertRaises(OSError):
            source.run('fact:bitcoin', failed, timeout=2)
        with self.assertRaises(TimeoutError):
            source.run('fact:oro', failed, timeout=2)
        self.assertEqual(calls, ['attempt'])
        self.assertEqual(source.run('another-provider', lambda: 'ok', timeout=2), 'ok')

    def test_invalid_zone_rejected(self):
        cfg = copy.deepcopy(DEFAULT)
        cfg['locale']['timezone'] = 'This/RegionDoesNotExist'
        with self.assertRaises(ValueError):
            load_config(cfg)
        with self.assertRaises(ValueError):
            validate_timezone('')


if __name__ == '__main__':
    unittest.main()
