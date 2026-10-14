import unittest
from resource_optimizer import config_limits,ollama_limits,get_intervals,PROFILES,process_usage
from settings import DEFAULT,load_config
from settings_effects import validate_form

class ResourceOptimizerLatestTests(unittest.TestCase):
    def test_default_budget_is_conservative_and_never_throttles_actor(self):
        cfg=load_config(DEFAULT)
        d=config_limits(cfg)
        self.assertEqual(d['performance_profile'],'Equilibrado')
        self.assertEqual(d['memory_budget_mb'],3072)
        self.assertLessEqual(d['model_context_tokens'],4096)
        self.assertNotIn('mt5_cycle_seconds',get_intervals(cfg))
        self.assertEqual(validate_form(cfg)['risk'],cfg['risk'])

    def test_profiles_control_ui_render_intervals(self):
        self.assertLess(PROFILES['Rendimiento']['render_seconds'],PROFILES['Ahorro de energía']['render_seconds'])
        self.assertLess(PROFILES['Rendimiento']['poll_ms'],PROFILES['Ahorro de energía']['poll_ms'])

    def test_cpu_only_and_model_unload_are_explicit(self):
        cfg=load_config(DEFAULT)
        cfg['desktop'].update(model_use_gpu=False,model_keep_alive_seconds=0,memory_budget_mb=1024,model_context_tokens=8192)
        options,keep=ollama_limits(cfg)
        self.assertEqual(options['num_gpu'],0)
        self.assertLessEqual(options['num_ctx'],2048)
        self.assertEqual(keep,'0s')
        self.assertNotIn('memory_hard_limit',options)

    def test_invalid_ram_limit_is_rejected_without_touching_trading(self):
        cfg=load_config(DEFAULT)
        cfg['desktop']['memory_budget_mb']=200000
        with self.assertRaisesRegex(ValueError,'memory_budget_mb'):validate_form(cfg)

    def test_soft_budget_handles_malformed_input(self):
        result=config_limits({'desktop':{'memory_budget_mb':'nan','model_keep_alive_seconds':'oops'}})
        self.assertEqual(result['memory_budget_mb'],3072)
        self.assertEqual(result['model_keep_alive_seconds'],15)

if __name__=='__main__':unittest.main()
