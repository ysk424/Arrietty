import base64
import io
import json
from pathlib import Path
import sys
import threading
import unittest
import urllib.error
import urllib.request
import wave

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from voice_service import OpenAI, Worker, VoiceError, make_server, strip_leading_signoff, validate_payload


def payload(silent=False):
    stream = io.BytesIO()
    with wave.open(stream, 'wb') as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(24000)
        wav.writeframes((b'\0\0' if silent else b'\1\0') * 12000)
    return {'audio': base64.b64encode(stream.getvalue()).decode(),
            'image': base64.b64encode(b'\xff\xd8\xfftest').decode(),
            'context': {'scene': 'test.blend', 'position_metres': [0, 1.5, 0]}}


class FakeOpenAI:
    def __init__(self):
        self.calls = []

    def transcribe(self, audio):
        self.calls.append(('whisper', audio))
        return 'この建物は何ですか。'

    def answer(self, text, image, context, history):
        self.calls.append(('vision', text, image, context, history))
        return '石造りの建物が見えます。'

    def speak(self, text):
        self.calls.append(('tts', text))
        return base64.b64decode(payload()['audio'])


class VoiceTests(unittest.TestCase):
    def test_signoff_removed_before_gpt_tts_display_and_history(self):
        client = FakeOpenAI()
        client.transcribe = lambda audio: 'ご視聴ありがとうございました。この建物は何ですか。'
        original_answer = client.answer
        def answer(*args):
            return 'ご視聴ありがとうございました！\n' + original_answer(*args)
        client.answer = answer
        worker = Worker(client)
        response = worker.ask(payload())
        self.assertEqual(client.calls[0][1], 'この建物は何ですか。')
        self.assertEqual(client.calls[1], ('tts', '石造りの建物が見えます。'))
        self.assertEqual(response['answer'], '石造りの建物が見えます。')
        self.assertEqual(worker.history[0]['content'], 'この建物は何ですか。')
        self.assertEqual(worker.history[1]['content'], '石造りの建物が見えます。')

    def test_signoff_only_is_not_sent_to_gpt_or_tts(self):
        client = FakeOpenAI()
        client.transcribe = lambda audio: 'ご視聴ありがとうございました。'
        with self.assertRaisesRegex(VoiceError, '認識結果が') as error:
            Worker(client).ask(payload())
        self.assertEqual(error.exception.recording['recognition'], 'signoff_only')
        self.assertEqual(client.calls, [])

    def test_digital_silence_does_not_call_api(self):
        client = FakeOpenAI()
        with self.assertRaisesRegex(VoiceError, '録音データは無音') as error:
            Worker(client).ask(payload(silent=True))
        self.assertTrue(error.exception.recording['silent'])
        self.assertEqual(client.calls, [])

    def test_quiet_audio_is_preserved_and_empty_asr_is_distinct(self):
        client = FakeOpenAI()
        response = Worker(client).ask(payload())  # 1 / 32768 amplitude is still sent.
        self.assertFalse(response['recording']['silent'])
        self.assertLess(response['recording']['peak_db'], -80)
        client.transcribe = lambda audio: ''
        with self.assertRaisesRegex(VoiceError, '言葉を認識できません') as error:
            Worker(client).ask(payload())
        self.assertEqual(error.exception.recording['recognition'], 'empty')

    def test_repeated_signoffs_and_ordinary_text(self):
        self.assertEqual(strip_leading_signoff('ご視聴ありがとうございました。 ご視聴ありがとうございました！ 説明です。'), '説明です。')
        ordinary = '最後に「ご視聴ありがとうございました」と表示されています。'
        self.assertEqual(strip_leading_signoff(ordinary), ordinary)

    def test_tts_produces_finalized_wav_for_godot(self):
        client = OpenAI()
        pcm = b'\1\0' * 24000
        client.request = lambda path, data: pcm
        result = client.speak('test')
        with wave.open(io.BytesIO(result), 'rb') as wav:
            self.assertEqual(wav.getframerate(), 24000)
            self.assertEqual(wav.getnframes(), 24000)
            self.assertEqual(wav.readframes(24000), pcm)
        self.assertEqual(int.from_bytes(result[4:8], 'little'), len(result) - 8)

    def test_image_audio_history_and_order(self):
        client = FakeOpenAI()
        worker = Worker(client)
        response = worker.ask(payload())
        self.assertEqual([call[0] for call in client.calls], ['whisper', 'vision', 'tts'])
        self.assertEqual(client.calls[1][2], payload()['image'])
        self.assertEqual(client.calls[1][3], payload()['context'])
        self.assertEqual(client.calls[1][4], [])
        self.assertTrue(base64.b64decode(response['audio']).startswith(b'RIFF'))
        worker.ask(payload())
        self.assertEqual(len(client.calls[4][4]), 2)

    def test_cancel_stops_before_gpt(self):
        client = FakeOpenAI()
        worker = Worker(client)
        original = client.transcribe
        def cancel(audio):
            worker.cancelled.set()
            return original(audio)
        client.transcribe = cancel
        with self.assertRaises(VoiceError):
            worker.ask(payload())
        self.assertEqual([call[0] for call in client.calls], ['whisper'])
        self.assertFalse(worker.lock.locked())

    def test_invalid_audio_and_image(self):
        for key in ('audio', 'image'):
            request = payload()
            request[key] = base64.b64encode(b'bad data').decode()
            with self.assertRaises((ValueError, wave.Error, EOFError)):
                validate_payload(request)

    def test_local_auth_and_nonblocking_cancel(self):
        client = FakeOpenAI()
        entered, release = threading.Event(), threading.Event()
        original = client.transcribe
        def delayed(audio):
            entered.set()
            release.wait(3)
            return original(audio)
        client.transcribe = delayed
        server = make_server('test-token', client)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        url = f'http://127.0.0.1:{server.server_port}'
        def post(path, token, data):
            req = urllib.request.Request(url + path, data=json.dumps(data).encode(),
                                         headers={'Authorization': 'Bearer ' + token})
            try:
                with urllib.request.urlopen(req, timeout=5) as res:
                    return res.status
            except urllib.error.HTTPError as exc:
                return exc.code
        try:
            self.assertEqual(post('/ask', 'wrong', payload()), 401)
            task = threading.Thread(target=lambda: post('/ask', 'test-token', payload()))
            task.start()
            self.assertTrue(entered.wait(2))
            self.assertEqual(post('/cancel', 'test-token', {}), 200)
            release.set()
            task.join(3)
            self.assertEqual([call[0] for call in client.calls], ['whisper'])
        finally:
            release.set()
            server.shutdown()
            server.server_close()


if __name__ == '__main__':
    unittest.main()
