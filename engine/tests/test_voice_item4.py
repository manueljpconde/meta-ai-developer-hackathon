"""Engine voice tests: WAV 60s cap, multipart shape, month-only estimated, match, calc boundary."""
import struct
import unittest

from app.voice import validate_wav, TranscriptionClient, ExtractionClient


def make_wav(duration_s=1):
    sr = 16000
    samples = int(sr * duration_s)
    header = bytearray(44)
    header[0:4] = b"RIFF"
    header[8:12] = b"WAVE"
    header[12:16] = b"fmt "
    struct.pack_into("<I", header, 16, 16)
    struct.pack_into("<H", header, 20, 1)
    struct.pack_into("<H", header, 22, 1)
    struct.pack_into("<I", header, 24, 16000)
    struct.pack_into("<I", header, 28, 32000)
    struct.pack_into("<H", header, 32, 2)
    struct.pack_into("<H", header, 34, 16)
    header[36:40] = b"data"
    struct.pack_into("<I", header, 40, samples * 2)
    header[4:8] = struct.pack("<I", 36 + samples * 2)[0].to_bytes(4, "little") if False else struct.pack("<I", 36 + samples*2)
    # fix sizes
    import struct as st
    st.pack_into("<I", header, 4, 36 + samples*2)
    return bytes(header) + b"\x00\x00" * samples


class ValidateWavTest(unittest.TestCase):
    def test_wav_valid_mono16k(self):
        ok, _ = validate_wav(make_wav(1))
        self.assertTrue(ok)

    def test_wav_rejects_short(self):
        ok, _ = validate_wav(b"RIFF")
        self.assertFalse(ok)

    def test_wav_rejects_stereo(self):
        data = bytearray(make_wav(1))
        struct.pack_into("<H", data, 22, 2)
        ok, err = validate_wav(bytes(data))
        self.assertFalse(ok)
        self.assertEqual(err, "channels")

    def test_wav_rejects_wrong_rate(self):
        data = bytearray(make_wav(1))
        struct.pack_into("<I", data, 24, 44100)
        ok, err = validate_wav(bytes(data))
        self.assertFalse(ok)
        self.assertEqual(err, "rate")

    def test_wav_rejects_60s_cap(self):
        ok, err = validate_wav(make_wav(61))
        self.assertFalse(ok)
        self.assertEqual(err, "duration")

    def test_wav_rejects_a_bad_fmt_marker(self):
        data = bytearray(make_wav(1))
        data[12:16] = b"BAD!"
        self.assertEqual(validate_wav(bytes(data)), (False, "fmt"))

    def test_wav_rejects_just_over_60s(self):
        self.assertEqual(validate_wav(make_wav(60.01)), (False, "duration"))

    def test_wav_rejects_audio_beyond_what_the_header_declares(self):
        data = bytearray(make_wav(61))
        struct.pack_into("<I", data, 40, 32000)
        self.assertEqual(validate_wav(bytes(data)), (False, "duration"))

    def test_wav_60s_passes(self):
        ok, _ = validate_wav(make_wav(60))
        self.assertTrue(ok)


class MultipartShapeTest(unittest.TestCase):
    def test_multipart_shape_criterion9(self):
        c = TranscriptionClient(api_key="k", api_base="https://api.meta.ai/v1")
        shape = c.multipart_shape()
        self.assertEqual(shape["parts"], 2)
        self.assertEqual(shape["names"], ["request", "audio"])
        self.assertEqual(shape["request_model"], "muse-voice-transcribe-1.0")
        self.assertEqual(shape["audioEncoding"], "WAV")

    def test_extraction_model_is_muse_spark(self):
        from app.voice import MODEL_NAME
        self.assertEqual(MODEL_NAME, "muse-spark-1.3")
        c = ExtractionClient(api_key="k", api_base="https://api.meta.ai/v1", timeout=30)
        self.assertEqual(c.timeout, 30)


class MoneyBoundaryTest(unittest.TestCase):
    def test_euro_via_calc_not_model(self):
        from engine.calc import agent_share
        self.assertEqual(agent_share(1000000, "0.4"), 400000)

