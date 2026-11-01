"""Interactive source reads must cancel and fit the local model's context."""
import tempfile,threading,time,unittest
from pathlib import Path
from unittest.mock import patch
from settings import DEFAULT,load_config
from assistant_akira import AkiraAssistant
from source_recovery import SourceDeadline


class ChatSources(unittest.TestCase):
    def test_tool_enabled_json_answer_reaches_the_visible_chat(self):
        import io,json
        from akira_local_ai import _post_direct_cancellable,visible_output
        reply={'choices':[{'message':{'role':'assistant','content':'He leído el fragmento.'},'finish_reason':'stop'}]}
        response=io.BytesIO(json.dumps(reply).encode());response.status=200
        seen=[]
        with patch('akira_local_ai.HTTPConnection') as connection,visible_output(seen.append):
            connection.return_value.getresponse.return_value=response
            result=_post_direct_cancellable('http://127.0.0.1:18996/v1/chat/completions',{'tools':[{}]},2,threading.Event())
        self.assertEqual(seen,['He leído el fragmento.']);self.assertEqual(result,reply)

    def test_cancel_releases_a_stuck_read_without_duplicating_it(self):
        jobs=SourceDeadline();cancel=threading.Event();release=threading.Event();entered=threading.Event();out=[]
        def reader():entered.set();release.wait(2);return 'late'
        def wait():
            try:jobs.run('feed',reader,3,cancel_event=cancel)
            except RuntimeError as error:out.append(str(error))
        worker=threading.Thread(target=wait);worker.start()
        try:
            self.assertTrue(entered.wait(1));cancel.set();worker.join(1)
            self.assertFalse(worker.is_alive());self.assertIn('detenido',out[0])
            with self.assertRaisesRegex(TimeoutError,'no se duplicará'):jobs.run('feed',reader,.01)
            self.assertEqual(jobs.run('other',lambda:'fresh',.1),'fresh')
        finally:release.set();worker.join(1)

    def test_integrated_video_read_uses_cancellable_caption_pages_without_a_nested_model(self):
        with tempfile.TemporaryDirectory() as tmp:
            bot=AkiraAssistant(load_config(DEFAULT),Path(tmp));body='Regla observada en el material. '*1000
            row={'url':'https://youtube.com/watch?v=fixture','title':'Fuente de prueba','body':body,'status':'transcript','complete':True,'kind':'youtube'}
            try:
                with patch('assistant_akira.read_youtube',return_value=row),patch('assistant_akira.analyze_youtube_video',side_effect=AssertionError('nested inference')):
                    result=bot._source_tool('analyze_youtube_video',{'url':row['url'],'topic':'prueba','offset':0})
                self.assertEqual(result['frames_analyzed'],0);self.assertFalse(result['analysis_complete'])
                self.assertFalse(result['excerpt_complete']);self.assertEqual(len(result['body']),2000)
                self.assertEqual(result['next_offset'],2000);self.assertEqual(bot.memory.get(row['url'])['body'],body)
            finally:bot._managed_model.shutdown()

    def test_cancelled_turn_cannot_start_a_new_public_read(self):
        with tempfile.TemporaryDirectory() as tmp:
            bot=AkiraAssistant(load_config(DEFAULT),Path(tmp));called=[];bot.cancel_current_reply()
            try:
                with self.assertRaisesRegex(RuntimeError,'detenido'):bot._read_public('read',lambda:called.append(1),.1)
                self.assertFalse(called)
            finally:bot._managed_model.shutdown()

    def test_total_public_read_budget_does_not_restart_for_each_tool(self):
        with tempfile.TemporaryDirectory() as tmp:
            bot=AkiraAssistant(load_config(DEFAULT),Path(tmp));bot._turn_budget.starts['sources']=time.monotonic()-61
            try:
                with self.assertRaisesRegex(TimeoutError,'plazo'):bot._read_public('read',lambda:'unused')
            finally:bot._managed_model.shutdown()


if __name__=='__main__':unittest.main()
