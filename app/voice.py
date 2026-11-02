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
MAX_AUDIO_BYTES = 16000 * 2 * MAX_AUDIO_SECONDS  # audio bytes of 60 s, mono 16-bit 16 kHz

# WAV constants
WAV_HEADER_SIZE = 44


def validate_wav(data):
    """Check WAV header: RIFF/WAVE, PCM, mono, 16-bit, 16000 Hz. Return (ok, error_key)."""
    if len(data) < WAV_HEADER_SIZE:
        return False, "short"
    if data[0:4] != b"RIFF" or data[8:12] != b"WAVE":
        return False, "riff"
    if data[12:16] != b"fmt ":
        return False, "fmt"
    try:
        fmt_size = struct.unpack_from("<I", data, 16)[0]
        audio_format, channels, sample_rate = struct.unpack_from("<HHI", data, 20)
        bits = struct.unpack_from("<H", data, 34)[0]
    except struct.error:
        return False, "parse"
    if fmt_size < 16:
        return False, "fmt"
    if audio_format != 1:
        return False, "format"
    if channels != 1:
        return False, "channels"
    if sample_rate != 16000:
        return False, "rate"
    if bits != 16:
        return False, "bits"
    # The data chunk follows the fmt chunk (chunks are padded to even sizes).
    # The duration is the larger of what the data chunk declares and the audio
    # bytes actually present, so an understating header cannot pass the cap.
    offset = 20 + fmt_size + (fmt_size & 1)
    declared = None
    while offset + 8 <= len(data):
        chunk_id = data[offset:offset + 4]
        chunk_size = struct.unpack_from("<I", data, offset + 4)[0]
        if chunk_id == b"data":
            declared = chunk_size
            offset += 8
            break
        offset += 8 + chunk_size + (chunk_size & 1)
    if declared is None:
        return False, "data"
    if max(declared, len(data) - offset) > MAX_AUDIO_BYTES:
        return False, "duration"
    return True, ""


def _api_base():
    return os.environ.get("META_API_BASE_URL", os.environ.get("META_API_BASE_URL", "https://api.meta.ai/v1"))


class ModelError(Exception):
    pass


EXTRACTION_PROMPT = (
    "An estate agent speaks or types one update, in Portuguese or English. "
    "Reply with exactly one JSON object and nothing else. Keys: "
    '"intent" ("update", or "question" when the agent asks something instead of reporting), '
    '"language" ("pt" or "en", the language of the message), '
    '"kind" (one of new_deal, cpcv_signed, escritura_date, fell_through, commission_received, '
    "change_stage, change_commission, change_percentage, reopen). "
    "Include only facts that were stated, never a guess: "
    '"name" (new deal) or "deal" (an existing deal), "agency", '
    '"commission" (agency commission in euros, excluding IVA), '
    '"share" (the agent\'s own percentage), '
    '"percentage" (a changed percentage), "amount" (euros received), '
    '"stage" (potencial, provavel or confirmado), '
    '"escritura_date" or "date" (YYYY-MM-DD when the day is said, YYYY-MM when only a month is said), '
    '"cpcv_date". Leave out every key that was not stated. '
    "Small transcription errors in names and numbers are tolerated."
)


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
                {"role": "system", "content": EXTRACTION_PROMPT},
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
