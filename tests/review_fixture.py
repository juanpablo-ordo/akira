"""Synthetic exact receipts for tests, never imported in production."""
from unittest.mock import Mock
from execution import Blocked
from execution_review import facts,fingerprint,validate,request_id

def approve_exact(engine,plan,volume,ticket=0,verdict='APPROVE'):
 prior=engine.context;capture=Mock();engine.context=capture
 try:
  try:engine.pending_review_guard(plan,engine.g.snapshot(),volume,ticket)
  except Blocked:pass
  proposals,snapshot=capture.request_pending_reviews.call_args.args
 finally:engine.context=prior
 p=proposals[0];e=facts(p,snapshot)
 data=validate({'verdict':verdict,'reason':'Synthetic exact-order verdict','contradictions':[],'evidence':['order.entry',next(k for k in e if k.startswith('H1.'))],'missing':[]},e)
 row={'state':'COMPLETE','fingerprint':fingerprint(p,snapshot),'updated':engine.g.clock(),'data':data}
 engine.planner.research_context.setdefault('pending_reviews',{})[request_id(p)]=row
 return row,p,snapshot
