import os
import unittest

from app.voice.remote_stt import RemoteSTT


class DummyClient:
    def __init__(self, output):
        self._output = output

    def automatic_speech_recognition(self, wav_bytes, model=None):
        # ignore inputs, just return the preconfigured object
        return self._output


class DummyResponse:
    def __init__(self, text):
        self._payload = {"text": text}

    def raise_for_status(self):
        pass

    def json(self):
        return self._payload


class RemoteSTTTests(unittest.TestCase):
    def setUp(self):
        # clear relevant environment variables for each test
        for var in ["STT_API", "HF_STT_MODEL", "HF_TOKEN", "OPENAI_API_KEY"]:
            os.environ.pop(var, None)

    def test_hf_dict_and_object(self):
        os.environ["STT_API"] = "hf"
        r = RemoteSTT()

        # return a dict
        r._get_hf_client = lambda: DummyClient({"text": "hello"})
        self.assertEqual(r.transcribe(b"ignored"), "hello")

        # return an object with attribute
        class WithAttr:
            text = "world"

        r._get_hf_client = lambda: DummyClient(WithAttr())
        self.assertEqual(r.transcribe(b"ignored"), "world")

    def test_hf_error_messages(self):
        os.environ["STT_API"] = "hf"
        r = RemoteSTT()

        # simulate StopIteration from HF client
        class BrokenClient:
            def automatic_speech_recognition(self, *_args, **_kwargs):
                raise StopIteration("no providers")

        r._get_hf_client = lambda: BrokenClient()
        with self.assertRaises(RuntimeError) as cm:
            r.transcribe(b"ignored")
        self.assertIn("no active providers", str(cm.exception))

        # simulate 404 error message
        class BrokenClient2:
            def automatic_speech_recognition(self, *_args, **_kwargs):
                raise Exception("404 not found")

        r._get_hf_client = lambda: BrokenClient2()
        with self.assertRaises(RuntimeError) as cm2:
            r.transcribe(b"ignored")
        self.assertIn("not available", str(cm2.exception))

    def test_openai_provider(self):
        os.environ["STT_API"] = "openai"
        os.environ["OPENAI_API_KEY"] = "fake"

        # fake requests.post
        class FakeResp2:
            def __init__(self, text):
                self._text = text

            def raise_for_status(self):
                pass

            def json(self):
                return {"text": self._text}

        def fake_post(url, headers=None, files=None, data=None):
            self.assertTrue(url.endswith("/audio/transcriptions"))
            return FakeResp2("openai-text")

        import app.voice.remote_stt as module
        module.requests.post = fake_post

        r = RemoteSTT()
        result = r.transcribe(b"whatever")
        self.assertEqual(result, "openai-text")

    def test_unknown_provider(self):
        os.environ["STT_API"] = "xyz"
        r = RemoteSTT()
        with self.assertRaises(RuntimeError) as cm3:
            r.transcribe(b"any")
        self.assertIn("unknown STT provider", str(cm3.exception))


if __name__ == "__main__":
    unittest.main()
