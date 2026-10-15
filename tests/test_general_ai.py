import copy
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from settings import DEFAULT
from assistant_akira import AkiraAssistant
from akira_local_ai import choose_text_model
from web_facts import lookup_current_fact, lookup_verified_current_fact


class AkiraGeneralAIRegressions(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name); self.cfg=copy.deepcopy(DEFAULT)
        # Legacy Ollama mocks test assistant logic; production defaults use managed llama.cpp.
        self.cfg["assistant"]["local_runtime_enabled"]=False

    def test_search_prefers_diverse_non_wikipedia_sources(self):
        rows=[
            {'title':'Wikipedia Xbox','url':'https://es.wikipedia.org/wiki/Xbox','text':'Xbox 2026 hardware'},
            {'title':'Xbox Wire','url':'https://news.xbox.com/a','text':'Xbox 2026 hardware oficial'},
            {'title':'The Verge','url':'https://www.theverge.com/a','text':'Xbox 2026 hardware lanzamiento'},
            {'title':'IGN','url':'https://www.ign.com/a','text':'Xbox 2026 hardware lanzamiento'},
        ]
        with patch('web_facts._duck_html',return_value=rows), patch('web_facts._bing_rss',return_value=[]), patch('web_facts._duck',return_value=[]), patch('web_facts._wiki',return_value=[]):
            out=lookup_current_fact('qué lanzó Xbox en 2026',limit=4)
        urls=[x['url'] for x in out['results']]
        self.assertTrue(urls)
        self.assertNotIn('wikipedia.org',urls[0])
        self.assertGreaterEqual(len({u.split('/')[2] for u in urls}),3)

    def test_source_followup_keeps_previous_topic(self):
        bot=AkiraAssistant(self.cfg,self.root)
        bot.history=[{'role':'user','text':'¿Qué lanzó Xbox en 2026?'},
                     {'role':'assistant','text':'Lanzó hardware.\n\nFuentes consultadas:\n[1] Xbox — https://news.xbox.com/a'}]
        seen=[]
        fake={'results':[{'title':'IGN','url':'https://www.ign.com/xbox','text':'Xbox 2026'}, {'title':'The Verge','url':'https://www.theverge.com/xbox','text':'Xbox 2026'}]}
        def source(name,args):
            if name=='research_public_web':seen.append(args['query']);return fake
            return {}
        with patch.object(bot,'_source_tool',side_effect=source), \
             patch('assistant_akira.ollama_status',return_value={'ok':True,'models':['qwen3:8b']}), \
             patch('assistant_akira.ollama_agent',return_value='Sí. IGN también cubrió el lanzamiento.'):
            answer=bot.reply('¿Puedes darme otras fuentes?',{},use_cloud=False)
        self.assertGreaterEqual(len(seen),2);self.assertEqual(seen[0],'¿Qué lanzó Xbox en 2026?');self.assertTrue(any('official source' in q or 'independent analysis' in q for q in seen[1:]))
        self.assertIn('ign.com',answer.lower())
        self.assertNotIn('news.xbox.com/a',answer)

    def test_verified_current_fact_accepts_official_without_year_plus_independent(self):
        official={'title':'Presidencia de Guatemala','url':'https://presidencia.gob.gt/presidente','text':'Presidente Bernardo Arévalo dirige el Gobierno de Guatemala.'}
        independent={'title':'Reuters','url':'https://www.reuters.com/world/americas/guatemala-x','text':'Guatemala President Bernardo Arevalo spoke on Tuesday.'}
        with patch('web_facts._duck_html',return_value=[official,independent]), patch('web_facts._bing_rss',return_value=[]), patch('web_facts._duck',return_value=[]), patch('web_facts._wiki',return_value=[]):
            out=lookup_verified_current_fact('presidente actual de Guatemala',limit=4)
        urls=[x['url'] for x in out['results']]
        self.assertIn(official['url'],urls)
        self.assertIn(independent['url'],urls)

    def test_specific_stable_fact_auto_researches(self):
        bot=AkiraAssistant(self.cfg,self.root); seen=[]
        fake={'results':[{'title':'Breaking Bad reference','url':'https://example.com/bb','text':'The scene identifies mercury fulminate.'}]}
        def source(name,args):
            if name=='research_public_web':seen.append(args['query']);return fake
            return {}
        with patch.object(bot,'_source_tool',side_effect=source), \
             patch('assistant_akira.ollama_status',return_value={'ok':True,'models':['qwen3:8b']}), \
             patch('assistant_akira.ollama_agent',return_value='En la escena se presenta fulminato de mercurio; no es nitroglicerina.'):
            answer=bot.reply('¿Qué explosivo usó Walter White con Tuco y cuál es su fórmula?',{},use_cloud=False)
        self.assertGreaterEqual(len(seen),2)
        self.assertIn('example.com/bb',answer)

    def test_python_howto_does_not_force_web(self):
        bot=AkiraAssistant(self.cfg,self.root)
        with patch.object(bot,'_source_tool',side_effect=AssertionError('no debe buscar web')), \
             patch('assistant_akira.ollama_status',return_value={'ok':True,'models':['qwen3:8b']}), \
             patch('assistant_akira.ollama_agent',return_value='Usa input(), float() y funciones para cada operación.'):
            answer=bot.reply('¿Cómo hago una calculadora en Python?',{},use_cloud=False)
        self.assertIn('input',answer)

    def test_host_owns_single_source_section(self):
        bot=AkiraAssistant(self.cfg,self.root)
        text='Respuesta.\n\nFuentes verificadas:\n- https://fake.example/x'
        rows=[{'title':'Oficial','url':'https://presidencia.gob.gt/x'}, {'title':'Reuters','url':'https://reuters.com/x'}]
        out=bot._append_source_list(text,rows)
        self.assertEqual(out.lower().count('fuentes'),1)
        self.assertNotIn('fake.example',out)
        self.assertIn('presidencia.gob.gt',out)
        self.assertIn('reuters.com',out)

    def test_visible_desktop_brand_is_only_akira(self):
        src=(Path(__file__).resolve().parents[1]/'desktop.py').read_text(encoding='utf-8')
        self.assertIn("root.title('AKIRA",src)
        self.assertNotIn('FINAL V6.0 PUBLIC AI',src)
        self.assertNotIn('AKIRA FINAL V6',src)

    def test_assistant_identity_is_akira_not_build_name(self):
        bot=AkiraAssistant(self.cfg,self.root)
        instructions=bot._instructions()
        self.assertIn('Eres Akira',instructions)
        self.assertNotIn('Eres AKIRA FINAL',instructions)

    def test_local_model_prefers_14b_when_installed(self):
        self.assertEqual(choose_text_model(['qwen3:14b','qwen3:8b'],'qwen3:8b','qwen3:4b'),'qwen3:14b')

    def test_installer_prepares_stronger_models_when_ram_allows(self):
        src=(Path(__file__).resolve().parents[1]/'PREPARAR_OLLAMA.ps1').read_text(encoding='utf-8-sig')
        self.assertIn("$ram -ge 40.0",src)
        self.assertIn("'qwen3:30b-a3b'",src)
        self.assertIn("'qwen3:14b'",src)


if __name__=='__main__':
    unittest.main()
