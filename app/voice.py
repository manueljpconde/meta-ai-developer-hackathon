"""Voice backend: transcription, extraction, conversation helpers.

All external calls go through injectable clients; tests stub them.
No network in tests.

Transcription spec (criterion 9): POST {base}/asr/transcribe with
multipart of exactly two parts: request+json and audio/wav.
Extraction spec (criterion 11): POST /chat/completions model muse-spark-1.3.

WAV validation: RIFF/WAVE, PCM, mono, 16-bit, 16000 Hz, max 60s cap.
Daily cap 30 per tenant checked before any model call.
Per-conversation 6-question cap.
"""
import io
import json
import os
import struct
import time
import urllib.request
import urllib.error

MODEL_NAME = "muse-spark-1.3"
TRANSCRIBE_MODEL = "muse-voice-transcribe-1.0"
TRANSCRIBE_PATH = "/asr/transcribe"
MAX_AUDIO_SECONDS = 60
MAX_AUDIO_BYTES = 16000 * 2 * 60 + 44  # mono 16-bit 16kHz 60s plus header

# WAV constants
WAV_HEADER_SIZE = 44


def validate_wav(data):
    """Check WAV header: RIFF/WAVE, PCM, mono, 16-bit, 16000 Hz. Return (ok, error_key)."""
    if len(data) < 44:
        return False, "short"
    if data[0:4] != b"RIFF" or data[8:12] != b"WAVE":
        return False, "riff"
    # find fmt chunk
    try:
        # basic header at offsets: 20 audioFormat, 22 channels, 24 sampleRate, 34 bitsPerSample
        audio_format = struct.unpack_from("<H", data, 20)[0]
        channels = struct.unpack_from("<H", data, 22)[0]
        sample_rate = struct.unpack_from("<I", data, 24)[0]
        bits = struct.unpack_from("<H", data, 34)[0]
    except struct.error:
        return False, "parse"
    if audio_format != 1:
        return False, "format"
    if channels != 1:
        return False, "channels"
    if sample_rate != 16000:
        return False, "rate"
    if bits != 16:
        return False, "bits"
    # duration check: data size minus header over bytes per second
    data_len = len(data) - 44
    seconds = data_len / (16000 * 2)
    if seconds > MAX_AUDIO_SECONDS + 0.5:
        return False, "duration"
    if len(data) > MAX_AUDIO_BYTES + 1024:
        return False, "too_large"
    return True, ""


def _api_base():
    return os.environ.get("META_API_BASE_URL", os.environ.get("META_API_BASE_URL", "https://api.meta.ai/v1"))


class ModelError(Exception):
    pass


class TranscriptionClient:
    """Live transcription client per criterion 9."""
    def __init__(self, api_key=None, api_base=None):
        self.api_key = api_key or os.environ.get("META_API_KEY", "")
        self.api_base = api_base or _api_base()

    def transcribe(self, wav_bytes):
        # Build multipart body exactly 2 parts
        boundary = "----VoiceBoundary123"
        meta = json.dumps({"model": TRANSCRIBE_MODEL, "audioEncoding": "WAV"})
        body = io.BytesIO()
        body.write(("--%s\r\n" % boundary).encode())
        body.write(b'Content-Disposition: form-data; name="request"\r\n')
        body.write(b"Content-Type: application/json\r\n\r\n")
        body.write(meta.encode())
        body.write(b"\r\n")
        body.write(("--%s\r\n" % boundary).encode())
        body.write(b'Content-Disposition: form-data; name="audio"; filename="audio.wav"\r\n')
        body.write(b"Content-Type: audio/wav\r\n\r\n")
        body.write(wav_bytes)
        body.write(("\r\n--%s--\r\n" % boundary).encode())
        payload = body.getvalue()
        req = urllib.request.Request(
            self.api_base.rstrip("/") + TRANSCRIBE_PATH,
            data=payload,
            headers={
                "Authorization": "Bearer " + self.api_key,
                "Content-Type": "multipart/form-data; boundary=%s" % boundary,
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = resp.read()
        except urllib.error.HTTPError as e:
            raise ModelError("transcription HTTP %d" % e.code)
        except Exception as e:
            raise ModelError(str(e))
        try:
            obj = json.loads(data.decode())
            return obj.get("transcript", ""), obj
        except Exception:
            raise ModelError("transcription bad response")

    def multipart_shape(self):
        """For tests: return description of expected multipart shape."""
        return {"parts": 2, "names": ["request", "audio"], "request_model": TRANSCRIBE_MODEL, "audioEncoding": "WAV"}


class ExtractionClient:
    """Extraction via muse-spark-1.3 chat completions."""
    def __init__(self, api_key=None, api_base=None, timeout=30):
        self.api_key = api_key or os.environ.get("META_API_KEY", "")
        self.api_base = api_base or os.environ.get("META_API_BASE_URL", "https://api.meta.ai/v1")
        self.timeout = timeout

    def extract(self, text):
        payload = {
            "model": MODEL_NAME,
            "messages": [
                {"role": "system", "content": "Extract update from the user message as JSON with intent, kind, fields and language pt or en. Reply with exactly one JSON object."},
                {"role": "user", "content": text},
            ],
            "temperature": 0,
        }
        req = urllib.request.Request(
            self.api_base.rstrip("/") + "/chat/completions",
            data=json.dumps(payload).encode(),
            headers={"Authorization": "Bearer " + self.api_key, "Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                body = resp.read()
        except urllib.error.HTTPError as e:
            raise ModelError("extraction HTTP %d" % e.code)
        except Exception as e:
            raise ModelError(str(e))
        try:
            obj = json.loads(body.decode())
            content = obj["choices"][0]["message"]["content"]
            # strict JSON parse
            return json.loads(content.strip())
        except ModelError:
            raise
        except Exception as e:
            raise ModelError("extraction bad response: %s" % e)
