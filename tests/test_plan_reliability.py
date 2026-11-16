import base64
import hashlib
import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from mt5_connection import confirmation_matches
from release_updates import (ReleaseTrust, UpdateError, canonical_json, download_installer,
                             verified_release)
from risk_limits import configured_limits, projected_margin
from settings import DEFAULT, desktop_release_config, load_config
from voice_session import audio_endpoint, audio_inventory, transcribe_with_recovery


class AudioRoutes(unittest.TestCase):
    def test_named_endpoint_survives_changed_index_and_default_uses_wasapi(self):
        host = {'name':'Windows WASAPI','default_input_device':-1,'default_output_device':0}
        display = {'name':'Monitor','hostapi':0,'max_output_channels':2}
        headphones = {'name':'Audífonos','hostapi':0,'max_output_channels':2}
        sd=SimpleNamespace(query_devices=lambda:[display,headphones],query_hostapis=lambda:[host])
        saved=next(row['key'] for row in audio_inventory(sd)['outputs'] if 'Audífonos' in row['name'])
        self.assertEqual(audio_endpoint(sd,saved,'output'),1)
        sd.query_devices=lambda:[headphones,display]
        host['default_output_device']=1
        self.assertEqual(audio_endpoint(sd,saved,'output'),0)
        self.assertEqual(audio_endpoint(sd,None,'output'),1)
        sd.query_devices=lambda:[display]
        with self.assertRaises(RuntimeError):
            audio_endpoint(sd,saved,'output')

    def test_uncertain_auto_recognition_does_not_become_a_question(self):
        model=SimpleNamespace(transcribe=lambda *_,**options:(
            [SimpleNamespace(text='texto espurio')],SimpleNamespace(language_probability=.30)))
        self.assertEqual(transcribe_with_recovery(model,[0.01]*9600,language=None),'')
        self.assertEqual(transcribe_with_recovery(model,[0.01]*9600,language='es'),'texto espurio')


class AccountAndRisk(unittest.TestCase):
    def test_migration_binds_valid_account_and_requires_neural_verdict(self):
        cfg=load_config(DEFAULT)
        cfg['execution']['review_policy']='technical'
        cfg['assistant']['provider_mode']='cloud'
        cfg['risk']['max_trade_pct']=.5
        cfg['mode']='trade'
        cfg['expected_login']=12345
        migrated=desktop_release_config(cfg)
        self.assertEqual(migrated['mode'],'observe')
        self.assertEqual(migrated['execution']['review_policy'],'required')
        self.assertEqual(migrated['assistant']['provider_mode'],'local')
        limit=configured_limits(migrated,{'balance':100,'equity':100,'currency':'EUR'})
        self.assertEqual((limit['per_trade'],limit['currency']),(.50,'EUR'))
        self.assertFalse(confirmation_matches((12345,'demo'),{'login':12345,'server':'real'}))

    def test_projected_margin_reserves_pending_exposure(self):
        account=SimpleNamespace(equity=100,margin=25,margin_free=75,currency='EUR')
        row=projected_margin(account,30,200)
        self.assertEqual(row['projected'],55)
        self.assertFalse(row['allowed'])
        self.assertTrue(projected_margin(account,20,200)['allowed'])


class LiveChartAndReplay(unittest.TestCase):
    def test_forming_bar_does_not_enter_closed_frame(self):
        from market_cache import MarketCache
        bar=lambda when,price:{'time':when,'open':price,'close':price,'high':price,'low':price,'tick_volume':1}
        api=SimpleNamespace(copy_rates_range=lambda *_:[bar(120,101),bar(180,200)])
        cache=MarketCache(api,'BTCUSDm',None,{})
        closed=cache.open_rates('M1',1,1,190)
        self.assertEqual([row['close'] for row in closed],[101])
        self.assertEqual(cache.forming['M1'].close,200)

    def test_bearish_sell_stop_records_adverse_fill_and_costs_only_in_replay(self):
        from strategy_lab import advance_case,definitions
        baseline=next(row for row in definitions() if row['id']=='LAB_BTC_BEAR_CONTINUATION_V1')
        self.assertFalse(baseline['auto_live_activation'])
        position={'state':'WAITING','plan':{'side':-1,'kind':'STOP','entry':100,'sl':105,'tp':90},
                  'created':20,'expiry_seconds':120,'horizon_seconds':300}
        position=advance_case(position,102,103,30,.05)
        self.assertEqual(position['state'],'WAITING')
        position=advance_case(position,99,100,35,.05)
        self.assertEqual(position['entry_price'],99)
        finished=advance_case(position,89,90,40,.05)
        self.assertEqual(finished['state'],'TP')
        self.assertAlmostEqual(finished['net_r'],1.75)


class SignedUpdate(unittest.TestCase):
    def setUp(self):
        self.key=Ed25519PrivateKey.generate()
        self.trust=ReleaseTrust('https://git.example/akira/stable.json',
            self.key.public_key().public_bytes_raw(),'CN=AKIRA','a'*64,(('git.example','/akira/'),))
        self.now=datetime.now(timezone.utc)
        self.exe=b'MZ'+b'installer data'
        self.manifest={'version':'0.2.0','minimum_version':'0.1.0','channel':'stable',
            'architecture':'windows-x64','commit':'a'*40,'sha256':hashlib.sha256(self.exe).hexdigest(),
            'size':len(self.exe),'url':'https://git.example/akira/setup.exe',
            'published_utc':(self.now-timedelta(hours=1)).isoformat(),
            'expires_utc':(self.now+timedelta(hours=1)).isoformat()}

    def signed(self,**changes):
        payload={**self.manifest,**changes}
        return canonical_json({'release':payload,
            'signature':base64.b64encode(self.key.sign(canonical_json(payload))).decode()})

    def test_channel_rejects_tampering_stale_foreign_and_older_releases(self):
        valid=self.signed()
        self.assertEqual(verified_release(valid,self.trust,'0.1.0',self.now).version,'0.2.0')
        tampered=json.loads(valid)
        tampered['release']['size']+=1
        for invalid,installed in [(canonical_json(tampered),'0.1.0'),
            (self.signed(url='https://mirror.example/setup.exe'),'0.1.0'),
            (self.signed(expires_utc=self.now.isoformat()),'0.1.0'),
            (valid,'0.3.0')]:
            with self.assertRaises(UpdateError):
                verified_release(invalid,self.trust,installed,self.now)

    def test_file_hash_must_match_before_authenticode(self):
        release=verified_release(self.signed(),self.trust,'0.1.0',self.now)
        with tempfile.TemporaryDirectory() as directory:
            target=Path(directory)/('AKIRA-'+release.version+'-'+self.manifest['sha256']+'.exe')
            target.write_bytes(b'x'*len(self.exe))
            with patch('release_updates.authenticode') as auth:
                with self.assertRaises(UpdateError):
                    download_installer(directory,release,self.trust,lambda:False)
                auth.assert_not_called()


if __name__=='__main__':
    unittest.main()
