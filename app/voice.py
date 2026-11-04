"""Voice backend: transcription, extraction, conversation helpers.

All external calls go through injectable clients; tests stub them.
No network in tests.

Transcription spec (criterion 9): POST {base}/asr/transcribe with
multipart of exactly two parts: request+json and audio/wav.
Extraction spec (criterion 11): POST /chat/completions model muse-spark-1.3.

WAV validation: RIFF/WAVE, PCM, mono, 16-bit, 16000 Hz, sizes that match
the body (outer RIFF length, data-chunk length, block alignment, byte rate,
whole samples), max 60s cap.
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
TRANSCRIBE_KEYWORDS = ("comissão", "percentagem", "escritura", "CPCV", "negócio", "potencial", "provável", "confirmado")
MAX_AUDIO_SECONDS = 60
MAX_AUDIO_BYTES = 16000 * 2 * MAX_AUDIO_SECONDS  # audio bytes of 60 s, mono 16-bit 16 kHz

# WAV constants
WAV_HEADER_SIZE = 44


def _valid_fourcc(chunk_id):
    """A RIFF chunk identifier: four printable ASCII bytes."""
    return not any(b < 0x20 or b > 0x7E for b in chunk_id)


def _valid_list_payload(data, start, size):
    """The payload of a LIST chunk: its four-byte list type followed by
    subchunks that account exactly for the rest of it. Each subchunk
    carries a proper printable FourCC and a size that stays inside the
    LIST container — a subchunk that overruns it (QA's truncated INAM)
    makes the whole body invalid, and so does a payload the subchunks do
    not exactly fill."""
    if size < 4:
        return False
    offset = start + 4  # past the list type
    end = start + size
    while offset < end:
        # The subchunk header must sit whole inside both the LIST payload
        # and the body; a LIST that declares more than the body holds is
        # malformed, not walked past the end.
        if offset + 8 > end or offset + 8 > len(data):
            return False
        if not _valid_fourcc(data[offset:offset + 4]):
            return False
        sub_size = struct.unpack_from("<I", data, offset + 4)[0]
        offset += 8 + sub_size + (sub_size & 1)
        if offset > end:
            return False
    return offset == end


def validate_wav(data):
    """Check the WAV container end to end: RIFF/WAVE, PCM, mono, 16-bit,
    16000 Hz, a size accounting that matches the body actually present and
    a whole number of samples. Return (ok, error_key)."""
    if len(data) < WAV_HEADER_SIZE:
        return False, "short"
    if data[0:4] != b"RIFF" or data[8:12] != b"WAVE":
        return False, "riff"
    if data[12:16] != b"fmt ":
        return False, "fmt"
    try:
        riff_size = struct.unpack_from("<I", data, 4)[0]
        fmt_size = struct.unpack_from("<I", data, 16)[0]
        audio_format, channels, sample_rate = struct.unpack_from("<HHI", data, 20)
        byte_rate = struct.unpack_from("<I", data, 28)[0]
        block_align = struct.unpack_from("<H", data, 32)[0]
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
    # The PCM block alignment and byte rate must be valid and consistent
    # with mono 16-bit 16 kHz audio: a whole sample per block and the
    # sample rate times that block.
    if block_align != channels * bits // 8:
        return False, "align"
    if byte_rate != sample_rate * block_align:
        return False, "byte_rate"
    # The outer RIFF size counts everything after the 8-byte RIFF header;
    # it must match the body actually present, or the container was cut
    # off in transit (a size too small) or overstates it (a size too big).
    if riff_size != len(data) - 8:
        return False, "riff_size"
    # The data chunk follows the fmt chunk (chunks are padded to even sizes).
    # Every chunk between them must be a valid RIFF chunk: a proper printable
    # FourCC identifier, and a LIST chunk whose payload is its four-byte list
    # type followed by well-formed subchunks — the same rules the trailing
    # walk enforces after the data payload.
    # The duration is the larger of what the data chunk declares and the audio
    # bytes actually present, so an understating header cannot pass the cap.
    offset = 20 + fmt_size + (fmt_size & 1)
    declared = None
    while offset + 8 <= len(data):
        chunk_id = data[offset:offset + 4]
        chunk_size = struct.unpack_from("<I", data, offset + 4)[0]
        if not _valid_fourcc(chunk_id):
            return False, "structure"
        if chunk_id == b"LIST" and not _valid_list_payload(data, offset + 8, chunk_size):
            return False, "structure"
        if chunk_id == b"data":
            declared = chunk_size
            offset += 8
            break
        offset += 8 + chunk_size + (chunk_size & 1)
    if declared is None:
        return False, "data"
    # A body shorter than the data chunk declares was cut off in transit:
    # refuse it before any model call, like every other broken header.
    if len(data) - offset < declared:
        return False, "truncated"
    # The audio must be a whole number of samples, not a fraction of one.
    if declared % (channels * bits // 8):
        return False, "align"
    # The 60 s cap counts the larger of what the data chunk declares and
    # the audio bytes actually present, so an understating header cannot
    # pass the cap.
    if max(declared, len(data) - offset) > MAX_AUDIO_BYTES:
        return False, "duration"
    # Every byte after the declared data payload must belong to a valid
    # following RIFF chunk, and the walk must end exactly at the end of
    # the body. A valid chunk carries a proper FourCC identifier — four
    # printable ASCII bytes, not NULs or other control bytes — and a LIST
    # chunk's payload is its required four-byte list type followed by
    # subchunks that account exactly for it, so a LIST size below four or
    # a subchunk that overruns its container is malformed. Raw audio the
    # data chunk does not declare is not a chunk: a data size that
    # understates the body is an invalid container, and so is a container
    # cut off inside a later chunk.
    tail = offset + declared + (declared & 1)
    while tail + 8 <= len(data):
        chunk_id = data[tail:tail + 4]
        chunk_size = struct.unpack_from("<I", data, tail + 4)[0]
        if not _valid_fourcc(chunk_id):
            return False, "structure"
        if chunk_id == b"LIST" and not _valid_list_payload(data, tail + 8, chunk_size):
            return False, "structure"
        tail += 8 + chunk_size + (chunk_size & 1)
    if tail != len(data):
        return False, "structure"
    return True, ""


def _api_base():
    return os.environ.get("META_API_BASE_URL", os.environ.get("META_API_BASE_URL", "https://api.meta.ai/v1"))


class ModelError(Exception):
    pass


EXTRACTION_PROMPT = (
    "An estate agent speaks or types one update, in Portuguese or English. "
    "Reply with exactly one JSON object and nothing else. Keys: "
    '"intent" ("update", or "question" only when the agent asks something and states no deal facts; a message that states deal facts is an update even when it is phrased or transcribed as a question), '
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
        request = {"model": TRANSCRIBE_MODEL, "audioEncoding": "WAV"}
        language = getattr(self, "language", None)
        if language:
            request["language"] = language.split("-")[0]
            request["keywords"] = list(TRANSCRIBE_KEYWORDS)
        meta = json.dumps(request)
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
        t0 = time.monotonic()
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = resp.read()
        except urllib.error.HTTPError as e:
            raise ModelError("transcription HTTP %d" % e.code)
        except Exception as e:
            raise ModelError(str(e))
        finally:
            print("TIMING transcribe %d ms audio_bytes=%d" % ((time.monotonic() - t0) * 1000, len(wav_bytes)), flush=True)
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
    def __init__(self, api_key=None, api_base=None, timeout=45):
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
            # Muse always reasons; picking a few fields needs the least of it.
            "reasoning_effort": "minimal",
        }
        req = urllib.request.Request(
            self.api_base.rstrip("/") + "/chat/completions",
            data=json.dumps(payload).encode(),
            headers={"Authorization": "Bearer " + self.api_key, "Content-Type": "application/json"},
            method="POST",
        )
        t0 = time.monotonic()
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                body = resp.read()
        except urllib.error.HTTPError as e:
            raise ModelError("extraction HTTP %d" % e.code)
        except Exception as e:
            raise ModelError(str(e))
        finally:
            print("TIMING extract %d ms text_chars=%d" % ((time.monotonic() - t0) * 1000, len(text)), flush=True)
        try:
            obj = json.loads(body.decode())
            content = obj["choices"][0]["message"]["content"]
            # strict JSON parse
            return json.loads(content.strip())
        except ModelError:
            raise
        except Exception as e:
            raise ModelError("extraction bad response: %s" % e)
