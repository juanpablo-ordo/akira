"""Update protocol with ephemeral test keys and isolated simulated installers.

No production key, real installer, trading connection or user profile is used.
Authenticode mocks model the OS boundary; they do not certify a Windows binary.
"""
import base64
import hashlib
import io
import json
import tempfile
import threading
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from notification_center import NotificationCenter
import release_updates as updates
import update_transaction as transaction
from tools.release_files import create_manifest, validate_build_run


class UpdateChannelTests(unittest.TestCase):
    def setUp(self):
        self.temporary=tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root=Path(self.temporary.name).resolve()
        self.key=Ed25519PrivateKey.generate()
        self.trust=updates.ReleaseTrust('https://example.com/akira/release.json',
            self.key.public_key().public_bytes_raw(),'CN=Test only','a'*64,
            (('example.com','/akira/'),))
        self.binary=b'MZ test-only installer bytes'
        now=datetime.now(timezone.utc)
        self.metadata={'version':'0.4.0','minimum_version':'0.1.0','channel':'stable',
            'architecture':'windows-x64','commit':'b'*40,'size':len(self.binary),
            'sha256':hashlib.sha256(self.binary).hexdigest(),
            'url':'https://example.com/akira/setup.exe',
            'published_utc':(now-timedelta(minutes=1)).isoformat(),
            'expires_utc':(now+timedelta(days=1)).isoformat()}

    def release(self, **changes):
        payload={**self.metadata,**changes}
        envelope=updates.canonical_json({'release':payload,
            'signature':base64.b64encode(self.key.sign(updates.canonical_json(payload))).decode()})
        return updates.verified_release(envelope,self.trust,'0.1.0')

    def response(self, data, status=200, headers=None):
        stream=io.BytesIO(data)
        stream.status=status
        stream.headers=headers or {}
        return stream

    def test_installed_version_is_up_to_date_instead_of_an_error(self):
        with patch.object(updates,'trusted_open',return_value=self.response(self.release().envelope)):
            self.assertIsNone(updates.check_channel(self.trust,'0.4.0'))

    def test_new_version_is_offered(self):
        with patch.object(updates,'trusted_open',return_value=self.response(self.release().envelope)):
            self.assertEqual(updates.check_channel(self.trust,'0.3.0').version,'0.4.0')

    def test_older_release_is_never_offered(self):
        with patch.object(updates,'trusted_open',return_value=self.response(self.release().envelope)):
            with self.assertRaises(updates.UpdateError):updates.check_channel(self.trust,'0.5.0')

    def test_signature_tampering_is_rejected_even_for_same_version(self):
        envelope=json.loads(self.release().envelope)
        envelope['release']['size']+=1
        with patch.object(updates,'trusted_open',return_value=self.response(updates.canonical_json(envelope))):
            with self.assertRaises(updates.UpdateError):updates.check_channel(self.trust,'0.4.0')

    def test_paused_download_resumes_and_checks_authenticode(self):
        release=self.release()
        stem='AKIRA-0.4.0-'+release.metadata['sha256']
        (self.root/(stem+'.pending.exe')).write_bytes(self.binary[:5])
        headers={'Content-Range':f'bytes 5-{len(self.binary)-1}/{len(self.binary)}'}
        with patch.object(updates,'trusted_open',return_value=self.response(self.binary[5:],206,headers)) as opened, \
                patch.object(updates,'authenticode') as auth:
            result=updates.download_installer(self.root,release,self.trust,lambda:False)
        self.assertEqual(result.read_bytes(),self.binary)
        self.assertEqual(opened.call_args.args[2]['Range'],'bytes=5-')
        auth.assert_called_once()

    def test_invalid_authenticode_never_promotes_download(self):
        with patch.object(updates,'trusted_open',return_value=self.response(self.binary)), \
                patch.object(updates,'authenticode',side_effect=updates.UpdateError('Rejected')):
            with self.assertRaises(updates.UpdateError):
                updates.download_installer(self.root,self.release(),self.trust,lambda:False)
        self.assertFalse(list(self.root.glob('AKIRA-*.exe')) and
                         any(not p.name.endswith('.pending.exe') for p in self.root.glob('AKIRA-*.exe')))

    def test_corrupted_download_is_rejected_before_os_signature(self):
        with patch.object(updates,'trusted_open',return_value=self.response(b'X'*len(self.binary))), \
                patch.object(updates,'authenticode') as auth:
            with self.assertRaises(updates.UpdateError):
                updates.download_installer(self.root,self.release(),self.trust,lambda:False)
        auth.assert_not_called()

    def run_transaction(self, health_error=None, wait_error=None):
        app=self.root/'application';app.mkdir()
        profile=self.root/'userdata';profile.mkdir()
        work=self.root/'job';work.mkdir()
        (app/'AKIRA.exe').write_bytes(b'previous version')
        (profile/'akira_config.json').write_text('{"saved":"settings"}')
        (profile/'chats.txt').write_text('saved chats')
        installer=profile/'state'/'updates'/'setup.exe'
        installer.parent.mkdir(parents=True);installer.write_bytes(self.binary)
        ticket=work/'update-job.json'
        ticket.write_bytes(updates.canonical_json({'app':str(app),'profile':str(profile),
            'installer':str(installer),'pid':123,
            'envelope':base64.b64encode(self.release().envelope).decode()}))
        def install(*args,**kwargs):
            (app/'AKIRA.exe').write_bytes(b'new version')
            (profile/'akira_config.json').write_text('{"migrated":true}')
            return SimpleNamespace(returncode=0)
        with patch('akira_version.RELEASE_VERSION','0.3.0'), \
                patch.object(updates.ReleaseTrust,'load',return_value=self.trust), \
                patch.object(transaction,'wait_for_app',side_effect=wait_error), \
                patch.object(transaction,'verify_installer'), \
                patch.object(transaction.subprocess,'run',side_effect=install), \
                patch.object(transaction,'validated_install',side_effect=health_error), \
                patch.object(transaction.subprocess,'Popen') as launch:
            result=transaction.run_install_job(ticket)
        return app,profile,work,result,launch

    def test_successful_transaction_reopens_new_version_with_original_profile(self):
        app,profile,work,result,launch=self.run_transaction()
        self.assertEqual(result,0)
        self.assertEqual((app/'AKIRA.exe').read_bytes(),b'new version')
        self.assertEqual((profile/'chats.txt').read_text(),'saved chats')
        self.assertEqual(launch.call_args.args[0],[str(app/'AKIRA.exe'),'--app-root',str(profile)])
        self.assertEqual(json.loads((profile/'state/update-result.json').read_bytes())['status'],'PASSED')

    def test_failed_health_restores_binaries_and_data_then_reopens(self):
        app,profile,work,result,launch=self.run_transaction(updates.UpdateError('Failed health'))
        self.assertEqual(result,1)
        self.assertEqual((app/'AKIRA.exe').read_bytes(),b'previous version')
        self.assertEqual(json.loads((profile/'akira_config.json').read_bytes()),{'saved':'settings'})
        self.assertEqual((profile/'chats.txt').read_text(),'saved chats')
        self.assertEqual(json.loads((work/'result.json').read_bytes())['status'],'RESTORED')
        launch.assert_called_once()

    def test_app_still_running_does_not_start_a_second_copy(self):
        app,profile,work,result,launch=self.run_transaction(wait_error=updates.UpdateError('Still running'))
        self.assertEqual(result,1)
        self.assertEqual((app/'AKIRA.exe').read_bytes(),b'previous version')
        launch.assert_not_called()

    def test_publisher_rejects_other_or_failed_builds(self):
        run={'status':'completed','conclusion':'success','head_sha':'b'*40,
            'head_branch':'akira-0.3-web-voz-recuperacion','event':'push',
            'path':'.github/workflows/build-windows.yml',
            'repository':{'full_name':'juanpablo-ordo/akira'},
            'head_repository':{'full_name':'juanpablo-ordo/akira'}}
        validate_build_run(run,'b'*40,'juanpablo-ordo/akira')
        for change in ({'conclusion':'failure'},{'head_sha':'c'*40},
                       {'head_branch':'main'},{'event':'pull_request'},
                       {'path':'other.yml'},{'head_repository':{'full_name':'other/fork'}}):
            with self.subTest(change=change),self.assertRaises(ValueError):
                validate_build_run({**run,**change},'b'*40,'juanpablo-ordo/akira')

    def test_manifest_binds_exact_signed_installer_and_commit(self):
        installer=self.root/'setup.exe';installer.write_bytes(self.binary)
        evidence={'status':'PASSED','release_version':'0.4.0','source_commit':'b'*40,
            'installer_sha256':self.metadata['sha256'],'installer_bytes':len(self.binary)}
        with patch('tools.release_files.RELEASE_VERSION','0.4.0'),patch('tools.release_files.authenticode'):
            envelope=create_manifest(installer,evidence,self.trust,self.key,self.metadata['url'],
                                     '0.3.0','Update notes','b'*40)
            self.assertEqual(updates.verified_release(envelope,self.trust,'0.3.0').version,'0.4.0')
            with self.assertRaises(ValueError):
                create_manifest(installer,evidence,self.trust,self.key,self.metadata['url'],
                                '0.3.0','Update notes','c'*40)
            installer.write_bytes(b'changed by signing')
            with self.assertRaises(ValueError):
                create_manifest(installer,evidence,self.trust,self.key,self.metadata['url'],
                                '0.3.0','Update notes','b'*40)

    def controller(self):
        from studio_controller import StudioController
        controller=StudioController.__new__(StudioController)
        controller._jobs=set();controller._jobs_lock=threading.Lock()
        controller.notices=NotificationCenter(self.root)
        controller.update_offer=None;controller.update_artifact=None
        controller.emitted=[]
        controller.emit=lambda kind,data:controller.emitted.append({'kind':kind,'data':data})
        def job(name,function,event=None,**kwargs):
            result=function()
            if event:controller.emit(event,result)
            return True
        controller.job=job
        return controller

    def test_automatic_check_emits_visible_notice_once_per_version(self):
        controller=self.controller()
        with patch.object(updates.ReleaseTrust,'load',return_value=self.trust), \
                patch.object(updates,'check_channel',return_value=self.release()):
            controller.check_updates();controller.check_updates()
        notices=[row for row in controller.emitted if row['kind']=='notice']
        self.assertEqual(len(notices),1)
        self.assertTrue(controller.emitted[-1]['data']['available'])
        self.assertFalse(controller.emitted[-1]['data']['explicit'])

    def test_periodic_check_does_not_interrupt_download_or_install(self):
        controller=self.controller()
        for name in ('download_update','install_update'):
            controller._jobs={name}
            with patch.object(updates,'check_channel') as check:
                self.assertFalse(controller.check_updates())
                check.assert_not_called()

    def test_up_to_date_check_clears_stale_offer(self):
        controller=self.controller();controller.update_offer=('stale',None)
        with patch.object(updates.ReleaseTrust,'load',return_value=self.trust), \
                patch.object(updates,'check_channel',return_value=None):
            controller.check_updates()
        self.assertIsNone(controller.update_offer)
        self.assertEqual(controller.emitted[-1]['data']['detail'],'AKIRA está actualizado.')


if __name__=='__main__':
    unittest.main()
