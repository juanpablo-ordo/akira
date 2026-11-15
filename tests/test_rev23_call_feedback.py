import builtins
import sys
import tempfile
import threading
import unittest
import wave
from types import SimpleNamespace
from unittest.mock import Mock, patch

from voice_conversation import CallConversation
from voice_session import VoiceSession, transcribe_with_recovery


class CallFeedbackTests(unittest.TestCase):
    def test_short_voice_retries_when_vad_misses_the_entire_utterance(self):
        model = Mock()
        model.transcribe.side_effect = [
            ([], None),
            ([SimpleNamespace(text='¿Me oyes?')], None),
        ]

        result = transcribe_with_recovery(model, [0.01] * 9600)

        self.assertEqual(result, '¿Me oyes?')
        self.assertTrue(model.transcribe.call_args_list[0].kwargs['vad_filter'])
        self.assertFalse(model.transcribe.call_args_list[1].kwargs['vad_filter'])

    def test_resuming_during_a_reply_keeps_the_microphone_gated(self):
        voice = VoiceSession('.', Mock(), {}, {})
        voice.pause()
        voice.start_response()
        voice.resume()

        self.assertFalse(voice.paused.is_set())
        self.assertTrue(voice.awaiting.is_set())
        voice.finish_response()
        self.assertFalse(voice.awaiting.is_set())

    def test_generated_answer_is_visible_even_when_audio_is_unavailable(self):
        voice = Mock()
        assistant = SimpleNamespace(chats=Mock())
        call = CallConversation(assistant, dict, dict, voice)

        call._reply('Recuerda que el oro es mi activo favorito.', threading.Event())

        voice.event.assert_called_once_with('answer', text='Lo recordaré.')
        voice.enqueue_speech.assert_called_once_with('Lo recordaré.')
        voice.finish_response.assert_called_once()

    def test_missing_inference_dependency_does_not_leave_the_call_busy(self):
        voice = Mock()
        call = CallConversation(Mock(), dict, dict, voice)
        call.busy = True
        original_import = builtins.__import__

        def import_without_inference(name, *args, **kwargs):
            if name == 'local_inference':
                raise ImportError('Dependencia de IA ausente')
            return original_import(name, *args, **kwargs)

        with patch('builtins.__import__', side_effect=import_without_inference):
            call._reply('¿Me oyes?', threading.Event())

        self.assertFalse(call.busy)
        self.assertEqual(voice.event.call_args.args[0], 'error')
        voice.finish_response.assert_called_once()

    def test_empty_wave_is_reported_before_playback(self):
        def write_empty_wave(request, _cancelled):
            with wave.open(request['path'], 'wb') as wav:
                wav.setparams((1, 2, 16000, 0, 'NONE', 'not compressed'))

        with tempfile.TemporaryDirectory() as root:
            events = []
            voice = VoiceSession(root, events.append, {'streaming_call': True}, {})
            synthesizer = SimpleNamespace(render=write_empty_wave, close=Mock())
            with patch('voice_session.SpeechServer', return_value=synthesizer), patch.dict(
                sys.modules, {'numpy': Mock(), 'sounddevice': Mock()}
            ):
                voice.speak('Esta respuesta debería producir audio.')
                voice._threads[-1].join(3)

            self.assertFalse(voice.speaking.is_set())
            self.assertNotIn('playback_start', [event['kind'] for event in events])
            self.assertTrue(
                any('audio vacío' in event.get('text', '') for event in events if event['kind'] == 'error')
            )


if __name__ == '__main__':
    unittest.main()
