"""Regression checks for resource profiles, MT5 no-op and conservative cleanup."""
import json
import tempfile
import unittest
from pathlib import Path

from resource_optimizer import get_intervals, PROFILES
from settings import DEFAULT, load_config
from settings_effects import validate_form
from install_release import cleanup_old_releases, inspect_old_releases
from tests.fixtures import PendingCase


class OptimizerTests(unittest.TestCase):
    def test_all_profiles_are_real_and_saving_loads_selection(self):
        levels=[get_intervals({'desktop':{'performance_profile':name}}) for name in
                ('Rendimiento','Equilibrado','Ahorro de energía')]
        self.assertEqual(len(PROFILES),3)
        self.assertLess(levels[0]['poll_ms'],levels[1]['poll_ms'])
        self.assertLess(levels[1]['poll_ms'],levels[2]['poll_ms'])
        self.assertLess(levels[0]['render_seconds'],levels[2]['render_seconds'])
        cfg=load_config(DEFAULT)
        cfg['desktop']['performance_profile']='Ahorro de energía'
        self.assertEqual(validate_form(cfg)['desktop']['performance_profile'],'Ahorro de energía')

    def test_unknown_profile_does_not_corrupt_state(self):
        cfg=load_config(DEFAULT)
        cfg['desktop']['performance_profile']='desconocido'
        with self.assertRaisesRegex(ValueError,'optimización'):
            validate_form(cfg)
        self.assertEqual(get_intervals(cfg),PROFILES['Equilibrado'])


class MT5NoChangeTests(PendingCase,unittest.TestCase):
    def test_identical_pending_price_levels_skip_broker_check_and_send(self):
        plan=self.plan();order=self.api.add_pending(plan)
        # The simulated broker must store tick-normalized fields, like real MT5.
        normalized,*_=self.g.validate_plan(plan,self.g.snapshot(),(int(order.ticket),),float(order.volume_current),editing=True)
        order.price_open,order.sl,order.tp=normalized.entry,normalized.sl,normalized.tp
        before=len(self.api.sent)
        self.assertTrue(self.g.pending_parameters_unchanged(order,
            {'price':order.price_open,'sl':order.sl,'tp':order.tp,'type_time':0}))
        self.cfg['mode']='trade'
        accepted=self.g.modify_pending(order,plan,'mejora propuesta')
        self.assertIsNone(accepted)
        self.assertEqual(len(self.api.sent),before)

    def test_distinct_real_tick_change_cannot_be_suppressed(self):
        plan=self.plan();order=self.api.add_pending(plan)
        self.assertFalse(self.g.pending_parameters_unchanged(order,
            {'price':order.price_open+.02,'sl':order.sl,'tp':order.tp,'type_time':0}))


class SafeCleanupTests(unittest.TestCase):
    def test_old_code_removed_only_after_backup_and_active_kept(self):
        with tempfile.TemporaryDirectory() as temp:
            home=Path(temp);runtime=home/'.akira_runtime';releases=runtime/'releases'
            active=releases/'Akira_ACTIVE';old=releases/'Akira_OLD';unknown=releases/'AnotherApp'
            for root in (active,old):
                root.mkdir(parents=True)
                for name,contents in [('Akira.py','app'),('akira_version.py','BUILD_ID="AKIRA_X"'),
                                      ('akira_config.json','{"test":1}')]:
                    (root/name).write_text(contents)
            (active/'RELEASE_READY.json').write_text('{}')
            (old/'state').mkdir();(old/'state'/'history.json').write_bytes(b'preserve')
            unknown.mkdir(parents=True);(unknown/'other.txt').write_text('untouched')
            (runtime/'active_install.json').write_text(json.dumps({'root':str(active)}))
            self.assertEqual(len(inspect_old_releases(runtime)['old_releases']),1)
            result=cleanup_old_releases(runtime,home/'Akira_Datos_Conservados')
            self.assertEqual(result['status'],'CLEANED')
            self.assertTrue(active.is_dir())
            self.assertFalse(old.exists())
            self.assertTrue((unknown/'other.txt').exists())
            backup=Path(result['removed'][0]['backup'])
            self.assertEqual((backup/'state'/'history.json').read_bytes(),b'preserve')

    def test_never_prune_without_verified_active_install(self):
        with tempfile.TemporaryDirectory() as temp:
            runtime=Path(temp)/'.akira_runtime';runtime.mkdir()
            with self.assertRaisesRegex(ValueError,'versión activada'):
                cleanup_old_releases(runtime,Path(temp)/'backups')
