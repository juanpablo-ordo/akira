"""Pending cockpit uses real engine fields and never invents broker tickets."""
import json,tempfile,tkinter as tk,unittest
from pathlib import Path
from desktop import Desktop
from settings import load_config,DEFAULT

class CandidateCockpit(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=tk.Tk();self.addCleanup(self.root.destroy)
        folder=Path(self.temp.name);cfg=load_config(DEFAULT)
        cfg['assistant']['auto_install_local_ai']=False
        cfg['desktop'].update(notifications=False,notification_sound=False,notification_popup=False)
        (folder/'akira_config.json').write_text(json.dumps(cfg),encoding='utf-8')
        self.app=Desktop(self.root,folder,preview=True,start_actor=False)
        self.app.navigate(1)
        self.root.update_idletasks()

    def payload(self,confirmed=False):
        idea={'symbol':'BTCUSDm','key':'SYNTHETIC-ONE','side':1,'kind':'LIMIT',
              'entry':100,'sl':90,'tp':130,'quality_score':70,'activation_score':45,
              'reason':'Soporte técnico no ejecutable sin revisión',
              'confirmed':confirmed,'ticket':98765 if confirmed else None,
              'sendable':not confirmed}
        return {'orders':[{'ticket':98765,'symbol':'BTCUSDm','owned':True}] if confirmed else [],'symbols':{'BTCUSDm':{'scenario_book':[idea]},'XAUUSDm':{'scenario_book':[]}},
                'pending_verifications':{},'execution_gate':{'code':'OBSERVE','reason':'Solo análisis','next_action':'Ajustes'}}

    def test_unconfirmed_is_not_displayed_as_sent(self):
        self.app.render_pending_overview(self.payload())
        tree=self.app.pending_overview
        self.assertEqual(len(tree.get_children()),1)
        self.assertEqual(tree.item(tree.get_children()[0],'values')[-1],'CANDIDATA VIABLE')
        self.assertIn('NO CONFIRMADA',self.app.pending_overview_detail.cget('text'))

    def test_stale_scenario_ticket_does_not_claim_order_still_at_broker(self):
        row=self.payload(True)
        row['orders']=[]
        self.app.render_pending_overview(row)
        state=self.app.pending_overview.item(self.app.pending_overview.get_children()[0],'values')[-1]
        self.assertEqual(state,'RECONCILIAR CON MT5')
        self.assertNotIn('CONFIRMADA MT5 #',state)

    def test_confirmed_must_have_ticket_and_selection_is_read_only(self):
        self.app.render_pending_overview(self.payload(True))
        tree=self.app.pending_overview
        self.assertEqual(len(tree.get_children()),1)
        self.assertIn('CONFIRMADA MT5 #98765',tree.item(tree.get_children()[0],'values')[-1])
        self.assertIn('MT5 #98765',self.app.pending_overview_detail.cget('text'))
        self.assertEqual(self.app.commands.qsize(),0)

if __name__=='__main__':unittest.main()
