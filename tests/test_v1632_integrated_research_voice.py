import tempfile,unittest,sqlite3
from unittest.mock import patch
import strategy_research
from pathlib import Path
from strategy_research import ResearchLedger
from akira_live2d import expression_for_voice_event,expression_for_dialogue

class ResearchTests(unittest.TestCase):
 def setUp(self):self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.ledger=ResearchLedger(self.temp.name)
 def test_all_sqlite_connections_closed_on_windows(self):
  """Windows WinError 32: closed SQLite connection must release the temp DB."""
  actual_connect=sqlite3.connect
  opened=[]
  class TrackedConnection(sqlite3.Connection):
   was_closed=False
   def close(self):
    self.was_closed=True
    return super().close()
  def tracked_connect(*args,**kwargs):
   kwargs['factory']=TrackedConnection
   connection=actual_connect(*args,**kwargs)
   opened.append(connection)
   return connection
  with tempfile.TemporaryDirectory() as folder:
   with patch('strategy_research.sqlite3.connect',side_effect=tracked_connect):
    ledger=strategy_research.ResearchLedger(folder)
    ledger.add(url='https://www.youtube.com/watch?v=abcdefghijk',kind='youtube_discovered')
    ledger.recent()
    ledger.summary()
   self.assertGreaterEqual(len(opened),4)
   self.assertTrue(all(c.was_closed for c in opened))
   ledger.path.unlink()  # Must also work on Windows; no SQLite file locks remain.

 def test_many_channels_and_news_without_authorizing_orders(self):
  for n in range(5):
   r=self.ledger.add(url=f'https://www.youtube.com/watch?v=test{n}',kind='youtube_discovered',title=f'Trader {n}',body='scalp and gold',status='discovered')
   self.assertFalse(r['complete_evidence']);self.assertFalse(r['live_authorized'])
  r=self.ledger.add(url='https://www.example.com/gold-news',kind='news_read',title='Gold',body='Reported observed facts '+ 'x'*900,status='read',symbols=['XAUUSDm','AUDUSDm'])
  self.assertTrue(r['complete_evidence']);self.assertEqual(r['symbols'],['XAUUSDm']);self.assertTrue(r['experiment_only'])
  summ=self.ledger.summary();self.assertEqual(summ['youtube'],5);self.assertEqual(summ['news'],1);self.assertFalse(summ['live_trading_from_sources'])
 def test_rejects_local_or_invalid_youtube(self):
  for url in ('file:///etc/passwd','http://127.0.0.1:3333','http://localhost/'):
   with self.assertRaises(ValueError):self.ledger.add(url=url,kind='news_read')
  with self.assertRaises(ValueError):self.ledger.add(url='https://example.com/watch?v=1',kind='youtube_transcript')
 def test_unverified_content_never_claims_learned_strategy(self):
  row=self.ledger.add(url='https://youtu.be/abcdefgh',kind='youtube_transcript',body='short',status='read',claims=['Risk all funds'])
  self.assertFalse(row['complete_evidence']);self.assertEqual(row['hypotheses'],[])

class VoiceReactionTests(unittest.TestCase):
 def test_voice_reactions(self):
  self.assertEqual(expression_for_voice_event('state','Micrófono activo · Escuchando'),'listening')
  self.assertEqual(expression_for_voice_event('state','Procesando tu mensaje'),'thinking')
  self.assertEqual(expression_for_voice_event('state','AKIRA responde'),'talking')
  self.assertEqual(expression_for_voice_event('state','Micrófono silenciado'),'sleeping')
  self.assertEqual(expression_for_voice_event('error','Dispositivo desconectó'),'alert')
  self.assertEqual(expression_for_voice_event('state','Llamada finalizada'),'idle')
 def test_context_questions(self):
  self.assertEqual(expression_for_dialogue('Analiza XAUUSDm','Veo algunas velas.'),'analyzing')
  self.assertEqual(expression_for_dialogue('Explica este concepto','Voy a responder.'),'thinking')
  self.assertEqual(expression_for_dialogue('Hola','Hola, bienvenido.'),'talking')
  self.assertEqual(expression_for_dialogue('Hola','Error: sin conexión'),'alert')

if __name__=='__main__':unittest.main()
