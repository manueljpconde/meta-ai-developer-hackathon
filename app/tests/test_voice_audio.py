"""V1: the recording path (item 4f).

The image has no JavaScript engine, so the algorithm lives in
app/voice_audio.py and is checked numerically here; the script served to the
page is checked to use the same constants and the same steps, and to wire
the audio context, the AudioWorklet and its fallback the way the criterion
says.
"""
import math
import pathlib
import re
import struct

from app import voice as voice_mod
from app import voice_audio as va
from app.tests.helpers import AppTestCase

ROOT = pathlib.Path(__file__).resolve().parents[1]
SCRIPT = (ROOT / "static" / "voice.js").read_text(encoding="utf-8")


def sine(rate, seconds, freq=440.0, amplitude=0.8):
    return [amplitude * math.sin(2 * math.pi * freq * i / rate) for i in range(int(rate * seconds))]


def measured_frequency(samples, rate):
    """Frequency from the zero crossings, ignoring the filter's edges."""
    edge = len(samples) // 20
    body = samples[edge:len(samples) - edge]
    crossings = sum(1 for a, b in zip(body, body[1:]) if (a < 0) != (b < 0))
    return crossings / 2.0 / (len(body) / float(rate))


def rms(samples):
    return math.sqrt(sum(s * s for s in samples) / len(samples))


class ResamplingTest(AppTestCase):
    def test_a_48000_hz_sine_keeps_its_frequency_and_duration_within_1_percent(self):
        self.check(48000)

    def test_a_44100_hz_sine_keeps_its_frequency_and_duration_within_1_percent(self):
        self.check(44100)

    def check(self, rate):
        seconds = 1.5
        out = va.resample(sine(rate, seconds), rate)
        self.assertLessEqual(abs(len(out) / 16000.0 - seconds) / seconds, 0.01)
        self.assertLessEqual(abs(measured_frequency(out, 16000) - 440.0) / 440.0, 0.01)

    def test_no_sample_is_dropped_or_repeated(self):
        for rate in (48000, 44100, 32000, 22050, 8000):
            count = rate  # one second
            out = va.resample([0.0] * count, rate)
            self.assertEqual(len(out), count * 16000 // rate, rate)
        # a ramp comes out increasing: nothing repeated, nothing out of order
        ramp = [i / 48000.0 for i in range(48000)]
        out = va.resample(ramp, 48000)
        steps = [b - a for a, b in zip(out[20:-20], out[21:-20])]
        self.assertTrue(all(step > 0 for step in steps))
        spread = max(steps) - min(steps)
        self.assertLess(spread, 1e-6)

    def test_the_level_is_kept_and_nothing_above_the_new_band_folds_back(self):
        out = va.resample(sine(48000, 1.0), 48000)
        self.assertLess(abs(rms(out[200:-200]) - 0.8 / math.sqrt(2)), 0.01)
        loud = va.resample(sine(48000, 1.0, freq=10000.0), 48000)
        self.assertLess(rms(loud[200:-200]), 0.05, "10 kHz must not alias into the speech band")

    def test_16_khz_in_is_16_khz_out_unchanged(self):
        samples = sine(16000, 0.1)
        self.assertEqual(va.resample(samples, 16000), samples)

    def test_a_slower_microphone_is_raised_to_16_khz_at_the_same_speed(self):
        out = va.resample(sine(8000, 1.0, freq=440.0), 8000)
        self.assertEqual(len(out), 16000)
        self.assertLessEqual(abs(measured_frequency(out, 16000) - 440.0) / 440.0, 0.01)

    def test_full_scale_and_silence_become_the_right_integers(self):
        self.assertEqual(va.to_int16(1.0), 32767)
        self.assertEqual(va.to_int16(-1.0), -32768)
        self.assertEqual(va.to_int16(2.5), 32767)
        self.assertEqual(va.to_int16(0.0), 0)


class WavHeaderTest(AppTestCase):
    def test_the_encoded_wav_states_16000_hz_mono_16_bit_and_the_right_data_size(self):
        samples = va.resample(sine(48000, 0.5), 48000)
        wav = va.encode_wav(samples)
        self.assertEqual(wav[0:4], b"RIFF")
        self.assertEqual(wav[8:16], b"WAVEfmt ")
        fmt_size, audio_format, channels, rate, byte_rate, align, bits = struct.unpack_from("<IHHIIHH", wav, 16)
        self.assertEqual((fmt_size, audio_format, channels, rate, bits), (16, 1, 1, 16000, 16))
        self.assertEqual((byte_rate, align), (32000, 2))
        self.assertEqual(wav[36:40], b"data")
        data_size = struct.unpack_from("<I", wav, 40)[0]
        self.assertEqual(data_size, len(samples) * 2)
        self.assertEqual(len(wav), 44 + data_size)
        self.assertEqual(struct.unpack_from("<I", wav, 4)[0], len(wav) - 8)

    def test_the_server_accepts_what_the_page_encodes(self):
        wav = va.encode_wav(va.resample(sine(44100, 1.0), 44100))
        self.assertEqual(voice_mod.validate_wav(wav), (True, ""))

    def test_the_samples_read_back_from_the_wav(self):
        wav = va.encode_wav([0.0, 0.5, -0.5, 1.0, -1.0])
        values = struct.unpack_from("<5h", wav, 44)
        self.assertEqual(values, (0, 16383, -16384, 32767, -32768))


class ServedScriptRecordingTest(AppTestCase):
    def served(self):
        response = self.client.get("/static/voice.js")
        self.assertEqual(response.code, 200)
        return response.body

    def constant(self, name):
        found = re.search(r"var %s = ([0-9.]+);" % name, SCRIPT)
        self.assertIsNotNone(found, name)
        return float(found.group(1))

    def test_the_script_and_the_reference_share_their_constants(self):
        self.assertEqual(self.constant("TARGET_RATE"), va.TARGET_RATE)
        self.assertEqual(self.constant("CUTOFF"), va.CUTOFF)
        self.assertEqual(self.constant("HALF_WIDTH"), va.HALF_WIDTH)

    def test_the_script_resamples_with_the_steps_of_the_reference(self):
        body = SCRIPT[SCRIPT.index("function downsample("):SCRIPT.index("function merge()")]
        compact = re.sub(r"\s+", "", body)
        for step in (
            "if(rate===TARGET_RATE){returnsamples;}",
            "varratio=rate/TARGET_RATE;",
            "varlen=Math.floor(samples.length*TARGET_RATE/rate);",
            "varcutoff=CUTOFF*Math.min(rate,TARGET_RATE)/rate;",
            "varhalf=HALF_WIDTH*Math.max(1,ratio);",
            "varcentre=i*ratio;",
            "varfirst=Math.max(Math.ceil(centre-half),0);",
            "varlast=Math.min(Math.floor(centre+half),samples.length-1);",
            "varw=weight(centre-j,cutoff,half);",
            "out[i]=norm?total/norm:0;",
        ):
            self.assertIn(step, compact)
        weight = re.sub(r"\s+", "", SCRIPT[SCRIPT.index("function weight("):SCRIPT.index("function downsample(")])
        for step in (
            "varx=2*cutoff*d;",
            "vars=x===0?1:Math.sin(Math.PI*x)/(Math.PI*x);",
            "return2*cutoff*s*(0.5+0.5*Math.cos(Math.PI*d/half));",
        ):
            self.assertIn(step, weight)

    def test_the_script_encodes_the_wav_with_the_steps_of_the_reference(self):
        body = re.sub(r"\s+", "", SCRIPT[SCRIPT.index("function encodeWav("):SCRIPT.index("// Windowed-sinc")])
        self.assertIn('str(12, "fmt ")', SCRIPT)
        for step in (
            "buf=newArrayBuffer(44+n*2)",
            'v.setUint32(4,36+n*2,true)', 'str(8,"WAVE")', 'str(0,"RIFF")',
            "v.setUint32(16,16,true)", "v.setUint16(20,1,true)", "v.setUint16(22,1,true)",
            "v.setUint32(24,TARGET_RATE,true)", "v.setUint32(28,TARGET_RATE*2,true)",
            "v.setUint16(32,2,true)", "v.setUint16(34,16,true)", 'str(36,"data")',
            "v.setUint32(40,n*2,true)",
            "v.setInt16(off,s<0?s*0x8000:s*0x7FFF,true)",
        ):
            self.assertIn(step, body)

    def test_the_rate_is_read_from_the_running_context_and_the_audio_track_never_assumed(self):
        self.assertIn("ctx.sampleRate", SCRIPT)
        self.assertIn("getSettings().sampleRate", SCRIPT)
        for assumed in (r"=\s*48000", r"=\s*44100", r":\s*48000", r":\s*44100", r"\|\|\s*48000", r"\|\|\s*44100"):
            self.assertNotRegex(SCRIPT, assumed)
        self.assertNotRegex(SCRIPT, r"new AC\(\{")
        self.assertIn("downsample(merge(), rate)", SCRIPT)

    def test_the_context_is_created_and_resumed_in_the_tap_before_getusermedia(self):
        tap = SCRIPT[SCRIPT.index("function onFalar()"):SCRIPT.index("fab.addEventListener")]
        self.assertIn("prepareAudio();", tap)
        self.assertLess(tap.index("prepareAudio();"), tap.index("listen(true);"))
        self.assertLess(tap.index("openPanel();"), tap.index("prepareAudio();"))
        prepare = SCRIPT[SCRIPT.index("function prepareAudio()"):SCRIPT.index("function listen(")]
        self.assertIn("new AC()", prepare)
        self.assertIn("ctx.resume()", prepare)
        self.assertNotIn("getUserMedia", prepare)
        listen = SCRIPT[SCRIPT.index("function listen("):SCRIPT.index("function onFalar()")]
        self.assertNotIn("new AC()", listen, "a context made outside a tap stays suspended on iOS")
        self.assertIn("getUserMedia", listen)
        # on the tap path, created and resumed before the microphone is asked for, in order of the source
        # (the iPhone restart after a spoken question asks for the microphone first, outside a tap)
        tap_mic = SCRIPT.index("getUserMedia", SCRIPT.index("function listen("))
        self.assertLess(SCRIPT.index("new AC()"), tap_mic)
        self.assertLess(SCRIPT.index("ctx.resume()"), tap_mic)

    def test_only_a_tap_may_create_the_context_and_other_turns_ask_for_one_tap(self):
        listen = SCRIPT[SCRIPT.index("function listen("):SCRIPT.index("function onFalar()")]
        self.assertIn("if (!ctx) { if (fromTap) { micBlocked(); } else { tapToAnswer(); } return; }", listen)

    def test_the_audio_goes_to_the_transcription_route_as_wav(self):
        self.assertIn('"/voice/transcribe?csrf_token="', SCRIPT)
        self.assertRegex(SCRIPT, r'headers: \{ "Content-Type": "audio/wav" \}, body: wav')
        self.assertIn("sendAudio(encodeWav(samples))", SCRIPT)

    def test_the_recording_uses_an_audioworklet_from_the_served_script(self):
        self.assertIn("ctx.audioWorklet.addModule(WORKLET_URL)", SCRIPT)
        self.assertIn('var WORKLET_URL = "/static/voice.js";', SCRIPT)
        self.assertIn('new AudioWorkletNode(ctx, "agentimo-recorder"', SCRIPT)
        # the same served file registers the processor when it runs in the worklet scope
        self.assertIn('registerProcessor("agentimo-recorder"', SCRIPT)
        self.assertIn('typeof registerProcessor === "function" && typeof document === "undefined"', SCRIPT)
        self.assertIn("AudioWorkletProcessor", SCRIPT)
        self.assertEqual(self.served(), SCRIPT)
        # the module path is the one route the page already has and CSP allows (default-src 'self')
        self.assertEqual(self.client.get("/static/voice.js").headers["content-security-policy"], "default-src 'self'")
        self.assertNotIn("blob:", SCRIPT)
        self.assertNotIn("data:", SCRIPT)

    def test_a_failed_worklet_is_reported_and_never_replaced_by_the_fallback(self):
        attach = SCRIPT[SCRIPT.index("function attach("):SCRIPT.index("function prepareAudio()")]
        worklet = SCRIPT[SCRIPT.index("function useWorklet()"):SCRIPT.index("function attach(")]
        # addModule rejecting: the panel's microphone message, not the ScriptProcessor
        self.assertRegex(attach, r"addModule\(WORKLET_URL\)\.then\(useWorklet, micBlocked\)")
        # the AudioWorkletNode constructor throwing: the same message
        self.assertIn("catch (e) { micBlocked(); }", worklet)
        self.assertNotIn("useScriptProcessor", worklet)
        # the one call to the fallback sits in the else branch, where AudioWorklet is missing
        self.assertEqual(attach.count("useScriptProcessor"), 1)
        self.assertIn("} else { useScriptProcessor(); }", attach)
        # the message comes from the panel's data attribute, which carries the page language
        mic = SCRIPT[SCRIPT.index("function micBlocked()"):SCRIPT.index("function useScriptProcessor()")]
        self.assertIn('panel.getAttribute("data-mic-blocked")', mic)

    def test_the_fallback_is_used_only_where_audioworklet_is_missing(self):
        attach = SCRIPT[SCRIPT.index("function attach("):SCRIPT.index("function prepareAudio()")]
        self.assertIn('ctx.audioWorklet && typeof AudioWorkletNode === "function"', attach)
        self.assertEqual(SCRIPT.count("createScriptProcessor"), 1)
        fallback = SCRIPT[SCRIPT.index("function useScriptProcessor()"):SCRIPT.index("function attach(")]
        self.assertIn("createScriptProcessor(4096, 1, 1)", fallback)
        # the fallback is reached from the branch where AudioWorklet is missing, and from nowhere else
        self.assertEqual(SCRIPT.count("useScriptProcessor()"), 2)  # its definition and the one call
        branch = attach[attach.index("if (ctx.audioWorklet"):]
        self.assertLess(branch.index("addModule"), branch.index("useScriptProcessor"))
        self.assertIn("else { useScriptProcessor(); }", attach)
