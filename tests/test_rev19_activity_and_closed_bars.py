"""Regressions for the photographed empty ActivityFeed tabs and closed-session bars."""
import unittest

from activity_events import category_for_event
from market_cache import MarketCache
from tests.fixtures import PendingCase


class ActivityCategories(unittest.TestCase):
    def test_explicit_category_is_authoritative_and_not_overridden_by_text(self):
        row={'category':'ANÁLISIS','state':'SISTEMA',
             'message':'ERROR and TRADING in the headline are not categories'}
        self.assertEqual(category_for_event(row),'ANÁLISIS')
        self.assertEqual(category_for_event({'activity_category':'ERROR',**row}),'ERROR')
        self.assertEqual(category_for_event({**row,'activity_category':'ERROR'}),'ERROR')

    def test_categories_reflect_structured_event_type(self):
        cases=[
            ({'state':'SISTEMA','symbol':'BTCUSDm'},'SISTEMA'),
            ({'operation':'protect','symbol':'XAUUSDm'},'TRADING'),
            ({'state':'MAPA','symbol':'BTCUSDm'},'ANÁLISIS'),
            ({'state':'RECHAZO MT5','symbol':'BTCUSDm'},'AVISO'),
            ({'severity':'ERROR','state':'DATOS'},'ERROR'),
            ({'message':'ERROR desactivado sin fallos'},'SISTEMA'),
            ({'state':'RUNNER','symbol':'XAUUSDm'},'TRADING'),
        ]
        for row,expected in cases:
            with self.subTest(row=row):
                self.assertEqual(category_for_event(row),expected)

    def test_filter_matches_the_same_category_painted_on_the_row(self):
        rows=[{'state':'MAPA'},{'operation':'protect'}, {'severity':'ERROR'}, {'state':'SISTEMA'}]
        indexed=[{**row,'activity_category':category_for_event(row)} for row in rows]
        for tab in ('TRADING','ANÁLISIS','ERROR','SISTEMA'):
            selected=[row for row in indexed if row['activity_category']==tab]
            self.assertEqual(len(selected),1)
            self.assertEqual(category_for_event(selected[0]),tab)


class ManagementConfigurationWarning(unittest.TestCase):
    def test_replay_export_does_not_claim_automatic_protection_active(self):
        from management_safety import protection_config_warning
        bad={'breakeven_at_r':10_000_000,'trail_at_r':100_000_000,'trail_atr':10_000}
        copy=dict(bad)
        warning=protection_config_warning(bad)
        self.assertIn('deshabilitada',warning)
        self.assertIn('breakeven=',warning)
        self.assertIn('trailing=',warning)
        self.assertEqual(bad,copy)  # never silently migrate the user's settings

    def test_normal_defaults_do_not_warn(self):
        from management_safety import protection_config_warning
        self.assertEqual(protection_config_warning(
            {'breakeven_at_r':1.25,'trail_at_r':1.8,'trail_atr':0.7}),'')


class AtomicResearchStorage(unittest.TestCase):
    def test_parallel_research_writers_keep_valid_json_and_clean_temps(self):
        from atomic_json import save_atomic_json
        from concurrent.futures import ThreadPoolExecutor
        from tempfile import TemporaryDirectory
        from pathlib import Path
        import json
        with TemporaryDirectory() as td:
            target=Path(td)/'state'/'pending_research.json'
            with ThreadPoolExecutor(max_workers=6) as pool:
                list(pool.map(lambda n: save_atomic_json(
                    target,{'sources':{'test':{'seq':n}}}),range(200)))
            document=json.loads(target.read_text(encoding='utf-8'))
            self.assertIn(document['sources']['test']['seq'],range(200))
            self.assertEqual(list(target.parent.glob('*.tmp')),[])

    def test_invalid_payload_does_not_replace_last_good_snapshot(self):
        from atomic_json import save_atomic_json
        from tempfile import TemporaryDirectory
        from pathlib import Path
        import json
        with TemporaryDirectory() as td:
            target=Path(td)/'pending_research.json'
            save_atomic_json(target,{'sources':{'ok':True}})
            circular={}
            circular['loop']=circular
            with self.assertRaises(ValueError):
                save_atomic_json(target,circular)
            self.assertEqual(json.loads(target.read_text(encoding='utf-8')),
                             {'sources':{'ok':True}})


class WeekendClosedBars(PendingCase,unittest.TestCase):
    def test_closed_session_reads_only_confirmed_bars(self):
        # FakeMT5 rejects start_pos=0 as an unclosed-bar read.
        # Move the wall clock beyond the synthetic H1 history.
        rows=self.api.rates[('XAUUSDm',16385)]
        self.clock.now=int(rows[-1]['time'])+4*86400
        cache=MarketCache(self.api,'XAUUSDm',self.g.log,self.cfg)
        cache.advance(self.clock.now,allowed=('H1',),closed_session=True)
        calls=[c for c in self.api.rate_calls if c[0]=='XAUUSDm']
        self.assertTrue(calls)
        self.assertTrue(all(c[2]==1 for c in calls))
        self.assertIn('H1',cache.frames)
        self.assertTrue(all(b.time+3600<=self.clock.now for b in cache.frames['H1'].bars))


if __name__=='__main__':unittest.main()
