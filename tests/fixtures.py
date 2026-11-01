import copy,json,tempfile,unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch
from settings import load_config,DEFAULT
from strategy import Plan
from execution import Gateway,Journal,Reporter,Blocked,PENDING,REMOVE,MODIFY,SLTP,DEAL,OWN_PENDING
from tests.fake_mt5 import Clock,FakeMT5

def optional_ollama_fixture(cfg):
    """Explicit legacy backend used ONLY by tests that mock the Ollama API."""
    cfg['assistant'].update(local_runtime_enabled=False,local_endpoint='http://127.0.0.1:11434/api/chat',
        local_model='qwen3:8b',local_model_lite='qwen3:4b',fast_chat_model='qwen3:8b')
    cfg['research']['local_ai_endpoint']='http://127.0.0.1:11434/api/chat'
    return cfg

class PendingCase:
    def setUp(self):
        self.review_stubs=[]
        if not getattr(self,'live_review_guard',False):
            # Transport fixtures isolate AI; dedicated Rev19 tests use the real guard.
            for target in ('engine.Engine.pending_review_guard','execution.Gateway.pending_review_guard'):
                stub=patch(target,create=True,return_value={'test_fixture':'APPROVED_TRANSPORT_ONLY'});stub.start();self.addCleanup(stub.stop);self.review_stubs.append(stub)
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.clock=Clock();self.api=FakeMT5(self.clock);self.cfg=load_config(DEFAULT);self.cfg['mode']='trade'  # fixtures de ejecución usan opt-in explícito
        optional_ollama_fixture(self.cfg)
        self.cfg['capital_protection']['enabled']=False  # transport fixtures test custom limits; Rev17 tests enable the capital policy
        self.cfg['execution']['pending_only']=True  # transport fixtures explicitly exercise the pending lane
        # La serie sintética base es deliberadamente simple y no contiene objetivos
        # swing H1/H4/D1 reales. Para pruebas de transporte/actor usamos un modo
        # permisivo SOLO dentro del fixture; las pruebas QUALITY-FIRST reactivan
        # explícitamente todas las puertas de producción.
        self.cfg['execution']['require_primary_structural_engine']=False
        self.cfg['execution']['require_observed_target']=False
        self.cfg['execution']['minimum_structural_grade']='B'
        for _sym,_rules in self.cfg.get('symbol_profiles',{}).items():
            _rules['pending_structural_quality_min']=78
            _rules['pending_structural_activation_min']=10
        self.g=Gateway(self.api,self.cfg,Journal(self.root/'state.json'),Reporter(self.root/'logs',console=False),self.clock)
    def plan(self,symbol='BTCUSDm',side=1,kind='LIMIT',key='SWING:1:LIMIT:H1:1'):
        ref=self.api.ticks[symbol].ask if side==1 else self.api.ticks[symbol].bid
        gap=20 if symbol.startswith('BTC') else .8;distance=100 if symbol.startswith('BTC') else 1
        entry=ref+side*gap*(-1 if kind=='LIMIT' else 1)
        return Plan(symbol,key,side,'PENDING',kind,entry,entry-side*distance,entry+side*distance*2,
                    gap,85,'MAPA STRUCTURAL H1',int(self.clock()),horizon_atr=distance,activation_score=75,quality_score=88)
    def assert_blocked(self,plan):
        with self.assertRaises(Blocked):self.g.send_immediate_plan(plan)
        self.assertEqual(self.api.sent,[])
