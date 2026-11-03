"""Reference for the recording path of the page script (app/static/voice.js).

The image that builds and tests this app has no JavaScript engine, so the
algorithm the page runs is written here, in Python, and checked numerically
by app/tests/test_voice_audio.py. voice.js implements the same constants and
the same steps; a second test reads the script and checks that they match.

Steps, in order, for the samples a microphone gave at its real rate:

1. Read the rate from the running audio context, never assume one.
2. Resample to 16 kHz with a windowed-sinc low-pass filter. Output sample i
   sits at input position i * rate / 16000. The output length is
   floor(n * 16000 / rate), so no sample is dropped or repeated and neither
   speed nor pitch changes. Frequencies above CUTOFF of the smaller rate are
   removed first, so nothing folds back into the speech band.
3. Convert to 16-bit integers and write a 44-byte WAV header that states
   16 000 Hz, mono, 16 bit and the data size.

``wav_stats`` is the server's side of the recording diagnostic: it reads the
numbers out of a WAV held in memory and keeps nothing.
"""
import math
import struct

TARGET_RATE = 16000
CUTOFF = 0.45       # of the smaller of the two rates, in cycles per second
HALF_WIDTH = 6      # filter reach each side, in periods of the slower rate
WAV_HEADER_SIZE = 44
MAX_RATE = 384000


def _weight(d, cutoff, half):
    """Windowed-sinc weight at distance d (input samples) from the centre."""
    x = 2 * cutoff * d
    s = 1.0 if x == 0 else math.sin(math.pi * x) / (math.pi * x)
    return 2 * cutoff * s * (0.5 + 0.5 * math.cos(math.pi * d / half))


def output_length(count, rate):
    return int(math.floor(count * TARGET_RATE / rate))


def resample(samples, rate):
    """Samples taken at ``rate`` Hz, returned at 16 kHz."""
    if rate == TARGET_RATE:
        return list(samples)
    ratio = rate / TARGET_RATE
    count = len(samples)
    out_len = output_length(count, rate)
    cutoff = CUTOFF * min(rate, TARGET_RATE) / rate
    half = HALF_WIDTH * max(1, ratio)
    out = []
    for i in range(out_len):
        centre = i * ratio
        first = max(int(math.ceil(centre - half)), 0)
        last = min(int(math.floor(centre + half)), count - 1)
        total = 0.0
        norm = 0.0
        for j in range(first, last + 1):
            w = _weight(centre - j, cutoff, half)
            total += w * samples[j]
            norm += w
        out.append(total / norm if norm else 0.0)
    return out


def to_int16(sample):
    """One float sample in -1..1 as a 16-bit integer (truncated, clamped)."""
    s = max(-1.0, min(1.0, sample))
    return int(s * 0x8000) if s < 0 else int(s * 0x7FFF)


def encode_wav(samples):
    """16 kHz mono 16-bit PCM WAV of float samples."""
    n = len(samples)
    header = b"RIFF" + struct.pack("<I", 36 + n * 2) + b"WAVE"
    header += b"fmt " + struct.pack("<IHHIIHH", 16, 1, 1, TARGET_RATE,
                                    TARGET_RATE * 2, 2, 16)
    header += b"data" + struct.pack("<I", n * 2)
    return header + struct.pack("<%dh" % n, *[to_int16(s) for s in samples])


def _data_chunk(wav):
    """(offset, declared size) of the data chunk, or the plain 44-byte layout."""
    if len(wav) >= 20 and wav[0:4] == b"RIFF" and wav[8:12] == b"WAVE":
        try:
            fmt_size = struct.unpack_from("<I", wav, 16)[0]
            offset = 20 + fmt_size + (fmt_size & 1)
            while offset + 8 <= len(wav):
                chunk_id = wav[offset:offset + 4]
                chunk_size = struct.unpack_from("<I", wav, offset + 4)[0]
                if chunk_id == b"data":
                    return offset + 8, chunk_size
                offset += 8 + chunk_size + (chunk_size & 1)
        except struct.error:
            pass
    return min(WAV_HEADER_SIZE, len(wav)), len(wav)


def wav_stats(wav):
    """(duration in seconds, peak 0..1) of the audio in a WAV held in memory.

    The duration counts the 16-bit samples actually present, at 16 kHz.
    Nothing is written or logged here or by the caller.
    """
    offset, declared = _data_chunk(wav)
    available = max(len(wav) - offset, 0)
    count = min(declared, available) // 2
    if count <= 0:
        return 0.0, 0.0
    peak = 0
    for (value,) in struct.iter_unpack("<h", wav[offset:offset + count * 2]):
        if value < 0:
            value = -value
        if value > peak:
            peak = value
    return round(count / TARGET_RATE, 2), round(min(peak / 32767.0, 1.0), 3)


def clean_rate(text):
    """The sample rate the page reported, as a whole number, or None."""
    try:
        rate = int(str(text).strip())
    except (TypeError, ValueError):
        return None
    return rate if 1 <= rate <= MAX_RATE else None
