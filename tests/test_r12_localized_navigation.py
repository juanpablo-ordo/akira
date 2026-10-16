import unittest
from localized_navigation import heading,subtitle,HEADINGS,SUBTITLES

class NavigationTranslations(unittest.TestCase):
    def test_every_builtin_locale_has_eight_nonempty_labels_and_details(self):
        self.assertEqual(set(HEADINGS),set(SUBTITLES))
        for loc in HEADINGS:
            self.assertEqual(len(HEADINGS[loc]),8)
            self.assertEqual(len(SUBTITLES[loc]),8)
            self.assertTrue(all(HEADINGS[loc]))
            self.assertTrue(all(SUBTITLES[loc]))
    def test_fallback_preserves_spanish_and_does_not_translate_prices(self):
        spanish=('Uno',)*8
        self.assertEqual(heading('ru',0,spanish),'Uno')
        self.assertEqual(subtitle('ru-RU',7,spanish),'Uno')
        self.assertEqual(heading('en',1,spanish),'PENDING ORDERS')

if __name__=='__main__':unittest.main()
