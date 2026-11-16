from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from uuid import uuid4

from mobile_companion import Companion, lan_identity
from privacy_guard import PrivacyPin, redacted_record


class CompanionTests(unittest.TestCase):
    def test_pairing_expiry_permissions_and_idempotence(self):
        now=[100.0]
        events=[]
        with TemporaryDirectory() as folder:
            pc=Companion(folder,lambda kind,event:events.append((kind,event)),clock=lambda:now[0])
            pc.actions['open_website']='https://example.com/sign-in'
            with self.assertRaises(PermissionError):
                pc.request('wrong.credential',{'id':str(uuid4()),'action':'status','expires':130})
            code=pc.pair()
            invite=pc.request_pairing(code,'Android test')
            self.assertEqual(pc.paired(invite['id'],invite['ticket'])['status'],'WAITING')
            with self.assertRaises(PermissionError):
                pc.request_pairing(code,'otro teléfono')
            pc.approve(invite['id'],{'status','open_website'})
            credential=pc.paired(invite['id'],invite['ticket'])['authorization']
            request={'id':str(uuid4()),'action':'open_website','expires':145}
            pc.request(credential,request)
            pc.request(credential,request)
            actions=[event for kind,event in events if kind=='mobile_action']
            self.assertEqual(len(actions),1)
            with patch.object(pc,'server',object()),patch('mobile_companion.webbrowser.open_new_tab',return_value=True) as browser:
                pc.confirm(actions[0],approved=True)
                pc.confirm(actions[0],approved=True)
                browser.assert_called_once_with('https://example.com/sign-in')
            self.assertEqual(pc.receipt(credential,request['id'])['status'],'Página abierta en el navegador')
            with self.assertRaises(PermissionError):
                pc.request(credential,{'id':str(uuid4()),'action':'open_application','expires':130})
            pc.revoke(invite['id'])
            with self.assertRaises(PermissionError):
                pc.receipt(credential,request['id'])
            expired=pc.pair()
            now[0]+=121
            with self.assertRaises(PermissionError):
                pc.request_pairing(expired,'demasiado tarde')

    def test_lan_identity_reuses_the_same_fingerprint(self):
        with TemporaryDirectory() as folder:
            first=lan_identity(folder,'192.168.15.4')
            again=lan_identity(folder,'192.168.15.4')
            self.assertEqual(first,again)
            self.assertEqual(len(first[2]),64)
            self.assertNotEqual(lan_identity(folder,'192.168.15.5')[2],first[2])


class PrivacyTests(unittest.TestCase):
    def test_pin_lockout_survives_restart_and_requires_windows_recovery(self):
        now=[10]
        with TemporaryDirectory() as folder:
            path=Path(folder)/'pin.json'
            pin=PrivacyPin(path,clock=lambda:now[0])
            pin.set_pin('456039','456039')
            self.assertNotIn('456039',path.read_text())
            for _ in range(3):
                self.assertFalse(pin.verify('111111'))
            pin=PrivacyPin(path,clock=lambda:now[0])
            with self.assertRaises(PermissionError):
                pin.verify('456039')
            now[0]+=10
            self.assertTrue(pin.verify('456039'))
            with self.assertRaises(PermissionError):
                pin.set_pin('095410','095410')
            pin.set_pin('095410','095410',windows_verified=True)
            self.assertTrue(pin.verify('095410'))

    def test_removes_private_url_parameters_and_keeps_public_video(self):
        data={'api_key':'señuelo','message':'https://youtube.com/watch?v=abcdefghijk&token=secreto'}
        self.assertEqual(redacted_record(data),{'message':'https://youtu.be/abcdefghijk'})
