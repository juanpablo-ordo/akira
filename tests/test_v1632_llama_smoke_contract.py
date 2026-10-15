"""Offline smoke contract: no false successes from an empty/thinking-only reply."""
import unittest

from installer.smoke_local_ai import make_chat_payload, validate_completion


class LlamaSmokeContractTests(unittest.TestCase):
    def test_requests_no_thinking_with_enough_tokens(self):
        payload = make_chat_payload()
        self.assertFalse(payload['chat_template_kwargs']['enable_thinking'])
        self.assertIn('/no_think', payload['messages'][0]['content'])
        self.assertGreaterEqual(payload['max_tokens'], 128)

    def test_accepts_visible_completed_answer(self):
        response = {'choices': [{'finish_reason': 'stop', 'message': {'content': 'Hola'}}]}
        self.assertEqual(validate_completion(response), 'Hola')

    def test_rejects_empty_but_with_reasoning(self):
        response = {'choices': [{'finish_reason': 'length',
                                 'message': {'content': '', 'reasoning_content': 'thinking'}}],
                    'usage': {'completion_tokens': 24}}
        with self.assertRaisesRegex(RuntimeError, 'reasoning_chars'):
            validate_completion(response)

    def test_rejects_think_without_visible_answer(self):
        response = {'choices': [{'finish_reason': 'stop', 'message': {'content': '<think>thinking</think>'}}]}
        with self.assertRaises(RuntimeError):
            validate_completion(response)

    def test_rejects_truncated_answer(self):
        response = {'choices': [{'finish_reason': 'length', 'message': {'content': 'Hola'}}]}
        with self.assertRaisesRegex(RuntimeError, 'finish_reason'):
            validate_completion(response)

    def test_accepts_visible_text_after_completed_thought(self):
        response = {'choices': [{'finish_reason': 'stop', 'message': {'content': '<think>reasoning</think>Hola'}}]}
        self.assertEqual(validate_completion(response), 'Hola')


if __name__ == '__main__':
    unittest.main()
