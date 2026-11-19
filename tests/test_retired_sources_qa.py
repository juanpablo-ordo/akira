"""Retired feeds cannot create new CoinGlass tasks or clutter the sources tab."""
import unittest
from research import ContextWorker
class RetiredSourcesQA(unittest.TestCase):
    def test_retired_vendor_is_never_enabled(self):
        worker=ContextWorker.__new__(ContextWorker)
        worker.cfg={'research':{'enabled':True,'coinglass':True,
                                 'derivatives_provider':'coinglass'},
                    'symbols':{'BTCUSDm':True,'XAUUSDm':True},
                    'assistant':{}}
        self.assertFalse(worker.source_enabled('coinglass:BTCUSDm'))
        self.assertFalse(worker.source_enabled('coinglass_heatmap:BTCUSDm'))
if __name__=='__main__':unittest.main()
