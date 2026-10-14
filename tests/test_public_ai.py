import json, tempfile, unittest
from pathlib import Path
from unittest.mock import patch
from assistant_akira import AkiraAssistant
import akira_local_ai

ROOT=Path(__file__).resolve().parents[1]

class TestFinalV6PublicAI(unittest.TestCase):
    def setUp(self):
        self.cfg=json.loads((ROOT/'akira_config.json').read_text(encoding='utf-8'))
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
    def tearDown(self):self.tmp.cleanup()

    def test_local_core_is_primary_and_cloud_optional(self):
        a=self.cfg['assistant'];self.assertTrue(a['local_primary']);self.assertFalse(a['cloud']);self.assertTrue(a['cloud_optional'])
        self.assertEqual(a['local_model_lite'],'qwen3:4b');self.assertEqual(a['local_vision_model'],'gemma3:4b')

    def test_public_ai_flags(self):
        v=self.cfg['final_v6'];self.assertTrue(v['enabled']);self.assertTrue(v['public_ai_local_first'])
        self.assertTrue(v['internet_tools_without_paid_api']);self.assertTrue(v['youtube_local_vision']);self.assertTrue(v['hot_loop_never_waits_for_llm'])

    def test_local_tools_include_web_reader_and_video(self):
        bot=AkiraAssistant(self.cfg,self.root)
        names={x['function']['name'] for x in bot._local_tools()}
        self.assertTrue({'research_public_web','read_public_source','read_youtube_transcript','analyze_youtube_video'}.issubset(names))

    def test_reply_prefers_local_before_cloud(self):
        bot=AkiraAssistant(self.cfg,self.root)
        with patch.object(bot,'local_llm_reply',return_value='respuesta local') as local, patch.object(bot,'cloud_reply',side_effect=AssertionError('cloud no debe ser primario')):
            self.assertEqual(bot.reply('Explícame qué es un agujero negro',{},use_cloud=True),'respuesta local')
            local.assert_called_once()

    def test_model_selection_falls_back_to_lite(self):
        self.assertEqual(akira_local_ai.choose_text_model(['qwen3:4b'],'qwen3:8b','qwen3:4b'),'qwen3:4b')
        self.assertEqual(akira_local_ai.choose_text_model(['qwen3:8b'],'qwen3:8b','qwen3:4b'),'qwen3:8b')

    def test_installer_bootstraps_local_ai(self):
        ps=(ROOT/'INSTALL_AKIRA.ps1').read_text(encoding='utf-8-sig')
        prep=(ROOT/'PREPARAR_OLLAMA.ps1').read_text(encoding='utf-8-sig')
        self.assertIn('PREPARAR_OLLAMA.ps1',ps);self.assertIn('qwen3:8b',prep);self.assertIn('qwen3:4b',prep);self.assertIn('gemma3:4b',prep)
        self.assertIn('TotalPhysicalMemory',prep)

    def test_local_video_is_default_path(self):
        src=(ROOT/'video_vision.py').read_text(encoding='utf-8')
        self.assertIn("engine':'AKIRA_LOCAL_VISION",src)
        self.assertIn("local_model='gemma3:4b'",src)
        self.assertIn('TRANSCRIPT_LOCAL_FALLBACK',src)

    def test_research_uses_local_context_module(self):
        src=(ROOT/'research.py').read_text(encoding='utf-8')
        self.assertIn('def _summary',src);self.assertIn('ollama_chat',src)
        self.assertIn("r.get('local_ai_summary',True)",src)

if __name__=='__main__':unittest.main()
