"""Real owned media lifecycle and selected strategy/review scheduling regressions."""
import copy,tempfile,time,unittest
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import Mock
from concurrent.futures import Future
from PIL import Image
from settings import DEFAULT,load_config
from tests.test_studio_rev5 import wait_for

class MediaAndSelection(unittest.TestCase):
    def test_nonlooping_gif_finishes_on_last_frame_and_releases_file(self):
        from studio_background import WallpaperWorker
        with tempfile.TemporaryDirectory() as t:
            p=Path(t)/'clip.gif';frames=[Image.new('RGB',(64,64),c) for c in ('red','green','blue')];frames[0].save(p,save_all=True,append_images=frames[1:],duration=100,loop=0)
            w=WallpaperWorker({'file':str(p),'kind':'gif','fps':10,'quality':100,'fit':'stretch','loop':False,'max_memory_mb':128,'max_cpu_percent':30},(64,64));w.start()
            try:
                self.assertTrue(wait_for(lambda:w.status.get('state') in ('ENDED','ERROR')));self.assertEqual(w.status.get('state'),'ENDED',w.status);self.assertTrue(w.frames);self.assertGreater(w.frames[-1][0][2],200)
            finally:w.close()
            p.unlink();self.assertFalse(p.exists())
    def test_rotation_zoom_and_gif_loop_keep_exact_frame_geometry(self):
        from studio_background import WallpaperWorker
        with tempfile.TemporaryDirectory() as t:
            p=Path(t)/'clip.gif';a=Image.new('RGB',(80,60),'red');a.save(p,save_all=True,append_images=[Image.new('RGB',(80,60),'blue')],duration=100,loop=0)
            w=WallpaperWorker({'file':str(p),'kind':'gif','fps':12,'quality':100,'fit':'contain','rotation':27,'zoom':130,'loop':True,'max_memory_mb':128,'max_cpu_percent':30},(160,100));w.start()
            try:
                self.assertTrue(wait_for(lambda:bool(w.frames) or w.status.get('state')=='ERROR'));self.assertNotEqual(w.status.get('state'),'ERROR',w.status);self.assertEqual(len(w.frames[-1][0]),160*100*3)
            finally:w.close()
            p.unlink()
    def test_selected_ema_variant_checks_conditions_and_rr_without_changing_levels(self):
        from strategy_lab import definitions
        from strategy_choice import variant_decision,allows
        d=next(d for d in definitions() if d.get('spec',{}).get('template')=='EMA_PULLBACK' and d['spec']['min_rr']==2.2)
        cfg=load_config(DEFAULT);cfg['strategy_choice']['selected']=d['id'];p=NS(side=1,entry=100,sl=97,tp=107,lane='PENDING',kind='LIMIT',reason='',key='BTC_PULLBACK')
        self.assertFalse(variant_decision(p,cfg,{})[0]);bars=[{'low':98,'high':101,'close':100,'open':99} for _ in range(24)];frames={'M15':{'atr':1,'bars':bars,'ema21':100,'rsi':50,'trend':.4},'H1':{'trend':.5}}
        before=vars(p).copy();self.assertTrue(variant_decision(p,cfg,frames)[0]);self.assertEqual(vars(p),before);p.tp=103;self.assertFalse(variant_decision(p,cfg,frames)[0])
    def test_custom_profile_does_not_override_newly_edited_colors(self):
        from studio_theme import palette_for
        studio=copy.deepcopy(load_config(DEFAULT)['studio']);studio.update(theme='Personalizado',accent='#123abc',secondary='#a01234',theme_profiles={'Personalizado':{'theme':'Nebulosa','accent':'#222222','secondary':'#333333'}})
        colors=palette_for(studio);self.assertEqual(colors['CYAN'],'#123abc');self.assertEqual(colors['PINK'],'#a01234')

class RequiredReviewPriority(unittest.TestCase):
    def setUp(self):
        from research import ContextWorker
        self.tmp=tempfile.TemporaryDirectory();self.worker=ContextWorker(load_config(DEFAULT),self.tmp.name,clock=lambda:1000);self.worker.pool=Mock();self.worker.pool.submit.return_value=Future()
    def tearDown(self):self.worker.close();self.tmp.cleanup()
    def test_required_review_runs_before_optional_batch(self):
        from pending_verification import identity
        plans=[{'symbol':'BTCUSDm','key':str(i),'side':1,'kind':'LIMIT','entry':100-i,'sl':90-i,'tp':120-i} for i in range(3)]
        snapshot={'symbols':{},'required_pending_reviews':[identity(plans[2])]};self.worker.request_pending_reviews(plans,snapshot);self.worker._pending_tick(1000,{})
        self.assertEqual(self.worker.pending_batch[0]['plan']['key'],'2');self.assertEqual(len(self.worker.pending_batch),2);self.assertNotEqual(self.worker.pending_reviews[identity(plans[2])]['state'],'COMPLETE')
    def test_already_queued_optional_review_is_promoted_without_duplicate_attempt(self):
        from pending_verification import identity
        p={'symbol':'BTCUSDm','key':'a','side':1,'kind':'LIMIT','entry':100,'sl':90,'tp':120};pid=identity(p);snapshot={'symbols':{}}
        self.worker.request_pending_reviews([p],snapshot);attempt=self.worker.pending_queue[pid]['attempt_id'];snapshot['required_pending_reviews']=[pid];self.worker.request_pending_reviews([p],snapshot)
        self.assertEqual(self.worker.pending_queue[pid]['priority'],0);self.assertEqual(self.worker.pending_queue[pid]['attempt_id'],attempt);self.assertEqual(len(self.worker.pending_queue),1)
