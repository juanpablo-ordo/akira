import unittest
from frozen_ui_contract import UI_MODULES

class FreezeModules(unittest.TestCase):
    def test_personalization_and_order_health_modules_are_explicitly_collected(self):
        self.assertTrue({'studio_theme','localized_navigation','operation_health','activity_watchdog'}.issubset(set(UI_MODULES)))

if __name__=='__main__':unittest.main()
