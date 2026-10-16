"""R9: failure states finish; user sprites process without network/MT5."""
import copy, tempfile, unittest
from pathlib import Path
from concurrent.futures import Future
from unittest.mock import Mock
from PIL import Image, ImageDraw
from akira_studio import import_sprites,suggested_sequences,split_sprites
from research import ContextWorker
from settings import load_config,DEFAULT as CONFIG
from pending_verification import assess,identity,fingerprint

class PendingTimeoutTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.clock=[1000.]
        self.worker=ContextWorker(load_config(CONFIG),self.temp.name,clock=lambda:self.clock[0])

    def test_queue_deadline_is_final_and_no_approval(self):
        self.worker.pending_reviews={'A':{'state':'QUEUED','requested':1000,'fingerprint':'f'},
                                     'B':{'state':'RUNNING','requested':1000,'started':1000,'fingerprint':'g'}}
        self.worker.pending_queue['A']={'plan':{}}
        self.clock[0]=1070
        self.assertEqual(self.worker.expire_pending_reviews(),['B'])
        self.assertEqual(self.worker.pending_reviews['B']['state'],'ERROR')
        self.assertIn('no se autoriza',self.worker.pending_reviews['B']['error'])
        self.clock[0]=1100
        self.assertEqual(self.worker.expire_pending_reviews(),['A'])
        self.assertNotIn('A',self.worker.pending_queue)
        self.assertEqual(self.worker.pending_reviews['A']['state'],'ERROR')
    def test_review_timeout_cannot_overwrite_with_late_success(self):
        self.worker.pending_reviews['A']={'state':'RUNNING','fingerprint':'f','started':1000,'requested':1000}
        self.clock[0]=1100;self.worker.expire_pending_reviews()
        # Expired result must remain terminal, even when a stale future succeeds.
        future=Future();future.set_result({'A':{'data':{'verdict':'APPROVE'}}})
        self.worker.pending_future=future;self.worker.pending_batch=[{'plan':{'symbol':'XAUUSDm','key':'a'},'fingerprint':'f'}]
        # The late result uses a different ID; no approval should be recorded.
        with self.worker.lock:self.worker._pending_tick(self.clock[0],{})
        self.assertEqual(self.worker.pending_reviews['A']['state'],'ERROR')

class SpriteImportTests(unittest.TestCase):
    def test_animated_gif_autogenerates_ordered_frames_and_sequence(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'personaje_habla.gif'
            frames=[Image.new('RGBA',(48,48),(100+i*30,20,50,255)) for i in range(3)]
            frames[0].save(path,save_all=True,append_images=frames[1:],duration=[100,150,200],loop=0)
            rows=import_sprites(Path(tmp),[path]);self.assertEqual(len(rows),3)
            self.assertEqual([r['state'] for r in rows],['talking']*3)
            seq=suggested_sequences(rows)
            self.assertEqual(seq['talking']['frames'],[r['id'] for r in rows])
            self.assertEqual(seq['talking']['delay_ms'],150)
    def test_sheet_split_automatically_and_manually(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'personaje_feliz.png'
            im=Image.new('RGBA',(144,64),(0,0,0,0));draw=ImageDraw.Draw(im)
            draw.rectangle((2,2,60,61),fill=(255,0,0,255))
            draw.rectangle((82,2,140,61),fill=(0,0,255,255));im.save(path)
            rows=import_sprites(Path(tmp),[path]);self.assertEqual(len(rows),2)
            self.assertEqual(len(import_sprites(Path(tmp),[path],rows)),2)
            seq=suggested_sequences(rows);self.assertIn('happy',seq)
            opaque=Image.new('RGBA',(96,96),(255,0,255,255));self.assertEqual(len(split_sprites(opaque)),1)
            self.assertEqual(len(split_sprites(opaque,rows=2,columns=2)),4)
    def test_user_sequences_not_overwritten(self):
        rows=[{'id':'a','source_group':'g','frame_index':0,'state':'idle','order':0},
              {'id':'b','source_group':'g','frame_index':1,'state':'idle','order':1}]
        old={'idle':{'frames':['b','a'],'delay_ms':200}}
        self.assertEqual(suggested_sequences(rows,old)['idle'],old['idle'])

class LanguagePackTests(unittest.TestCase):
    def test_custom_language_works_only_with_valid_pack(self):
        import json
        from akira_studio import DEFAULT,import_language_pack,read_language_pack,validate_studio
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp);input_file=path/'Russian.json'
            input_file.write_text(json.dumps({'locale':'ru-RU','translations':{'AJUSTES':'Настройки','TRADING':'Торговля'}},ensure_ascii=False),encoding='utf-8')
            stored,locale=import_language_pack(path,input_file)
            item=copy.deepcopy(DEFAULT);item['language_ui']=locale;item['language_pack']=stored
            self.assertEqual(validate_studio(item)['language_ui'],'ru-RU')
            self.assertEqual(read_language_pack(stored)['translations']['AJUSTES'],'Настройки')
            item['language_pack']=''
            with self.assertRaises(ValueError):validate_studio(item)
    def test_migration_rebases_custom_language_pack(self):
        import json
        from migrate_v11_settings import restore_user_data
        from akira_studio import DEFAULT,import_language_pack
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);before=root/'old';after=root/'new';before.mkdir()
            src=before/'Russian.json';src.write_text(json.dumps({'locale':'ru-RU','translations':{'TRADING':'Торговля'}},ensure_ascii=False),encoding='utf-8')
            pack,locale=import_language_pack(before,src)
            cfg=load_config(CONFIG);cfg['studio']['language_ui']=locale;cfg['studio']['language_pack']=pack
            from settings import save_config
            save_config(cfg,before/'akira_config.json')
            after.mkdir();(after/'akira_config.json').write_bytes((before/'akira_config.json').read_bytes())
            restore_user_data(before,None,after)
            loaded=load_config(after/'akira_config.json')
            self.assertTrue(Path(loaded['studio']['language_pack']).is_file())
            self.assertTrue(str(loaded['studio']['language_pack']).startswith(str(after)))

class ReviewAttemptIdentityTests(unittest.TestCase):
    def test_late_success_from_expired_attempt_cannot_confirm_new_attempt(self):
        with tempfile.TemporaryDirectory() as temp:
            w=ContextWorker(load_config(CONFIG),temp,clock=lambda:1500)
            req_old={'plan':{'symbol':'BTCUSDm','key':'id'},'fingerprint':'same','attempt_id':1}
            from pending_verification import identity
            pid=identity(req_old['plan'])
            w.pending_reviews[pid]={'fingerprint':'same','state':'RUNNING','attempt_id':2,'requested':1490}
            f=Future();f.set_result({pid:{'data':{'verdict':'APPROVE'}}})
            w.pending_future=f;w.pending_batch=[req_old]
            with w.lock:w._pending_tick(1500,{})
            self.assertNotIn('data',w.pending_reviews[pid]);self.assertEqual(w.pending_reviews[pid]['state'],'RUNNING')
