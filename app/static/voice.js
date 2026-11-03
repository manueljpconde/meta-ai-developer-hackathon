(function () {
  "use strict";
  // The same file is the AudioWorklet module: there it only registers the recorder.
  if (typeof registerProcessor === "function" && typeof document === "undefined") { registerRecorder(); return; }
  var $ = function (id) { return document.getElementById(id); };
  var panel = $("voicePanel");
  var fab = $("voiceFalar");
  var hdr = $("voiceFalarHeader");
  var transcriptEl = $("voiceTranscript");
  var questionEl = $("voiceQuestion");
  var readbackEl = $("voiceReadback");
  var confirmBtn = $("voiceConfirmBtn");
  var cancelBtn = $("voiceCancelBtn");
  var form = $("voiceTextForm");
  var input = $("voiceTextInput");
  var convId = $("voiceConvId");
  var diagEl = $("voiceDiag");
  var workingEl = $("voiceWorking");
  var backdrop = $("voiceBackdrop");
  var settingsFirst = $("voiceSettingsFirst");
  if (!panel || !form) { return; }
  var sendBtn = form.querySelector("button[type=submit]");
  var sendLabel = sendBtn ? sendBtn.textContent : "";
  var csrf = form.querySelector("input[name=csrf_token]").value;
  var TARGET_RATE = 16000;
  var CUTOFF = 0.45;
  var HALF_WIDTH = 6;
  var WORKLET_URL = "/static/voice.js";
  var MAX_SECONDS = 55;
  var SILENCE_SECONDS = 1.4;
  var NO_SPEECH_SECONDS = 10;
  var THRESHOLD = 0.02;

  var stream = null, ctx = null, source = null, proc = null, node = null, recRate = 0;
  var chunks = [], total = 0, speechSeen = false, silent = 0, listening = false;
  var speakTimer = null, busy = false;

  function encodeWav(samples) {
    var n = samples.length;
    var buf = new ArrayBuffer(44 + n * 2);
    var v = new DataView(buf);
    function str(off, s) { for (var i = 0; i < s.length; i++) { v.setUint8(off + i, s.charCodeAt(i)); } }
    str(0, "RIFF"); v.setUint32(4, 36 + n * 2, true); str(8, "WAVE");
    str(12, "fmt "); v.setUint32(16, 16, true); v.setUint16(20, 1, true);
    v.setUint16(22, 1, true); v.setUint32(24, TARGET_RATE, true);
    v.setUint32(28, TARGET_RATE * 2, true); v.setUint16(32, 2, true); v.setUint16(34, 16, true);
    str(36, "data"); v.setUint32(40, n * 2, true);
    var off = 44;
    for (var i = 0; i < n; i++) {
      var s = Math.max(-1, Math.min(1, samples[i]));
      v.setInt16(off, s < 0 ? s * 0x8000 : s * 0x7FFF, true);
      off += 2;
    }
    return buf;
  }

  // Windowed-sinc weight at distance d (input samples) from the output position.
  function weight(d, cutoff, half) {
    var x = 2 * cutoff * d;
    var s = x === 0 ? 1 : Math.sin(Math.PI * x) / (Math.PI * x);
    return 2 * cutoff * s * (0.5 + 0.5 * Math.cos(Math.PI * d / half));
  }

  // Samples taken at `rate` Hz, returned at 16 kHz: output i sits at input i * rate / 16000.
  function downsample(samples, rate) {
    if (rate === TARGET_RATE) { return samples; }
    var ratio = rate / TARGET_RATE;
    var len = Math.floor(samples.length * TARGET_RATE / rate);
    var cutoff = CUTOFF * Math.min(rate, TARGET_RATE) / rate;
    var half = HALF_WIDTH * Math.max(1, ratio);
    var out = new Float32Array(len);
    for (var i = 0; i < len; i++) {
      var centre = i * ratio;
      var first = Math.max(Math.ceil(centre - half), 0);
      var last = Math.min(Math.floor(centre + half), samples.length - 1);
      var total = 0, norm = 0;
      for (var j = first; j <= last; j++) {
        var w = weight(centre - j, cutoff, half);
        total += w * samples[j];
        norm += w;
      }
      out[i] = norm ? total / norm : 0;
    }
    return out;
  }

  // Runs inside the AudioWorklet: hands the microphone's samples to the page in blocks.
  function registerRecorder() {
    class Recorder extends AudioWorkletProcessor {
      constructor() {
        super();
        this.block = new Float32Array(2048);
        this.fill = 0;
      }
      process(inputs) {
        var channel = inputs[0] && inputs[0][0];
        if (channel) {
          for (var i = 0; i < channel.length; i++) {
            this.block[this.fill++] = channel[i];
            if (this.fill === this.block.length) {
              this.port.postMessage(this.block, [this.block.buffer]);
              this.block = new Float32Array(2048);
              this.fill = 0;
            }
          }
        }
        return true;
      }
    }
    registerProcessor("agentimo-recorder", Recorder);
  }

  function merge() {
    var all = new Float32Array(total), off = 0;
    for (var i = 0; i < chunks.length; i++) { all.set(chunks[i], off); off += chunks[i].length; }
    return all;
  }

  function setText(el, text) { el.textContent = text || ""; }

  function openPanel() { panel.hidden = false; }

  // The dimmed page behind the sheet on wide screens. A tap on it does nothing.
  function setBackdrop(on) { if (backdrop) { backdrop.hidden = !on; } }

  // Waiting is always visible: send is disabled and says so, and a line says the same.
  function setBusy(on) {
    busy = on;
    if (sendBtn) {
      sendBtn.disabled = on;
      sendBtn.textContent = on ? panel.getAttribute("data-thinking") : sendLabel;
    }
    if (workingEl) { setText(workingEl, on ? panel.getAttribute("data-thinking") : ""); }
    if (on) { setText(diagEl, ""); }
  }

  // Numbers only, from the server's answer: rate, seconds, level.
  function showDiagnostic(d) {
    if (!diagEl) { return; }
    if (!d) { setText(diagEl, ""); return; }
    var none = "\u2014";
    var line = panel.getAttribute("data-diag-line") || "";
    line = line.replace("{rate}", d.sample_rate ? d.sample_rate : none)
      .replace("{seconds}", d.duration_seconds !== undefined && d.duration_seconds !== null ? d.duration_seconds : none)
      .replace("{peak}", d.peak !== undefined && d.peak !== null ? d.peak : none);
    setText(diagEl, line);
  }

  // No saved settings: one line and a link, nothing to type.
  function showSettingsFirst() {
    if (settingsFirst) { settingsFirst.hidden = false; }
    form.hidden = true;
  }

  function releaseMic() {
    listening = false;
    try { if (proc) { proc.disconnect(); proc.onaudioprocess = null; } } catch (e) {}
    try { if (node) { node.disconnect(); node.port.onmessage = null; } } catch (e) {}
    try { if (source) { source.disconnect(); } } catch (e) {}
    try { if (stream) { stream.getTracks().forEach(function (t) { t.stop(); }); } } catch (e) {}
    try { if (ctx && ctx.close) { ctx.close(); } } catch (e) {}
    stream = ctx = source = proc = node = null;
  }

  function stopSpeech() {
    if (speakTimer) { clearTimeout(speakTimer); speakTimer = null; }
    try { if (window.speechSynthesis) { window.speechSynthesis.cancel(); } } catch (e) {}
  }

  function resetView() {
    setText(transcriptEl, ""); setText(questionEl, ""); setText(readbackEl, "");
    setText(diagEl, ""); setText(workingEl, "");
    confirmBtn.hidden = true;
    convId.value = "";
  }

  function closePanel(reload) {
    stopSpeech(); releaseMic(); panel.hidden = true; setBackdrop(false); resetView();
    if (reload) { window.location.reload(); }
  }

  function pickVoice(lang) {
    var voices = [];
    try { voices = window.speechSynthesis.getVoices() || []; } catch (e) {}
    var prefix = lang.split("-")[0].toLowerCase();
    var i;
    for (i = 0; i < voices.length; i++) { if (voices[i].lang === lang) { return voices[i]; } }
    for (i = 0; i < voices.length; i++) {
      if (voices[i].lang && voices[i].lang.toLowerCase().indexOf(prefix) === 0) { return voices[i]; }
    }
    return null;
  }

  function speak(text, lang, done) {
    if (!text || !window.speechSynthesis || typeof SpeechSynthesisUtterance === "undefined") {
      done(); return;
    }
    var finished = false;
    function finish() {
      if (finished) { return; }
      finished = true;
      if (speakTimer) { clearTimeout(speakTimer); speakTimer = null; }
      done();
    }
    try {
      window.speechSynthesis.cancel();
      var u = new SpeechSynthesisUtterance(text);
      u.lang = lang || "pt-PT";
      var voice = pickVoice(u.lang);
      if (voice) { u.voice = voice; }
      u.onend = finish;
      u.onerror = finish;
      speakTimer = setTimeout(finish, 15000);
      window.speechSynthesis.speak(u);
    } catch (e) { finish(); }
  }

  function post(url, params) {
    var body = new URLSearchParams();
    body.append("csrf_token", csrf);
    body.append("format", "json");
    Object.keys(params).forEach(function (k) { body.append(k, params[k]); });
    return fetch(url, {
      method: "POST", credentials: "same-origin",
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
      body: body.toString()
    }).then(readAnswer);
  }

  // An answer the server sent is never "No connection": 413 is too long, a non-JSON answer is a refusal.
  function readAnswer(r) {
    if (r.status === 413) { return { state: "error", message: panel.getAttribute("data-too-long") }; }
    return r.text().then(function (text) {
      try { return JSON.parse(text); } catch (e) {
        return { state: "error", message: panel.getAttribute("data-server-refused") };
      }
    });
  }

  // Only a request that never reached the server shows the connection message.
  function failed() {
    setBusy(false);
    setText(questionEl, panel.getAttribute("data-network-error"));
  }

  function render(d) {
    setBusy(false);
    if (d.state === "settings_first") { setText(questionEl, ""); showSettingsFirst(); return; }
    showDiagnostic(d.diagnostic);
    if (d.conversation_id !== undefined) { convId.value = d.conversation_id; }
    if (d.transcript !== undefined) {
      setText(transcriptEl, d.understood ? d.transcript + "\n" + d.understood : d.transcript);
    }
    var lang = d.lang || document.documentElement.lang || "pt-PT";
    if (d.state === "saved") { closePanel(true); return; }
    if (d.state === "cancelled") {
      confirmBtn.hidden = true; setText(readbackEl, ""); setText(questionEl, d.message);
      stopSpeech(); releaseMic();
      setTimeout(function () { closePanel(true); }, 1800);
      return;
    }
    if (d.state === "ask") {
      confirmBtn.hidden = true; setText(readbackEl, ""); setText(questionEl, d.question);
      speak(d.question, lang, listen);
      return;
    }
    if (d.state === "confirm") {
      setText(questionEl, ""); setText(readbackEl, d.readback);
      confirmBtn.hidden = false;
      speak(d.readback, lang, listen);
      return;
    }
    confirmBtn.hidden = true; setText(readbackEl, "");
    setText(questionEl, d.message || "");
    if (d.state === "ended") { convId.value = ""; }
    speak(d.message, lang, function () {});
  }

  function sendText(text) {
    if (busy) { return; }
    stopSpeech(); finishListening(false);
    setBusy(true);
    post("/voice/extract", { conversation_id: convId.value, text: text }).then(render, failed);
  }

  function sendAudio(wav) {
    setBusy(true);
    var url = "/voice/transcribe?csrf_token=" + encodeURIComponent(csrf) +
      "&format=json&conversation_id=" + encodeURIComponent(convId.value) +
      "&sample_rate=" + encodeURIComponent(Math.round(recRate));
    fetch(url, {
      method: "POST", credentials: "same-origin",
      headers: { "Content-Type": "audio/wav" }, body: wav
    }).then(readAnswer).then(render, failed);
  }

  function finishListening(send) {
    if (!listening) { return; }
    listening = false;
    if (send && total > 0) {
      var rate = recRate;
      if (!(rate > 0)) { chunks = []; total = 0; micBlocked(); return; }
      var samples = downsample(merge(), rate);
      chunks = []; total = 0;
      sendAudio(encodeWav(samples));
    } else {
      chunks = []; total = 0;
    }
  }

  // The rate the samples really have: the running context's, else the audio track's. Never assumed.
  function realRate() {
    var rate = ctx ? ctx.sampleRate : 0;
    if (!(rate > 0) && stream) {
      try { rate = stream.getAudioTracks()[0].getSettings().sampleRate; } catch (e) { rate = 0; }
    }
    return rate > 0 ? rate : 0;
  }

  function onSamples(data) {
    if (!listening) { return; }
    chunks.push(data); total += data.length;
    var sum = 0;
    for (var i = 0; i < data.length; i++) { sum += data[i] * data[i]; }
    var rms = Math.sqrt(sum / data.length);
    var rate = recRate;
    if (rms > THRESHOLD) { speechSeen = true; silent = 0; } else { silent += data.length; }
    if (speechSeen && silent > SILENCE_SECONDS * rate) { finishListening(true); return; }
    if (total > MAX_SECONDS * rate) { finishListening(true); return; }
    if (!speechSeen && total > NO_SPEECH_SECONDS * rate) { finishListening(false); tapToAnswer(); }
  }

  // A browser that will not restart the microphone by itself shows one tap per answer.
  function tapToAnswer() {
    if (!questionEl.textContent) { setText(questionEl, panel.getAttribute("data-tap-answer")); }
  }

  function startRecording() {
    recRate = realRate();
    if (!(recRate > 0)) { micBlocked(); return; }
    chunks = []; total = 0; speechSeen = false; silent = 0; listening = true;
    if (ctx && ctx.state === "suspended" && ctx.resume) {
      var resumed = ctx.resume();
      if (resumed && resumed.catch) { resumed.catch(function () { listening = false; tapToAnswer(); }); }
    }
  }

  function micBlocked() {
    releaseMic();
    setText(questionEl, panel.getAttribute("data-mic-blocked"));
  }

  function useScriptProcessor() {
    try {
      proc = ctx.createScriptProcessor(4096, 1, 1);
      proc.onaudioprocess = function (e) { onSamples(new Float32Array(e.inputBuffer.getChannelData(0))); };
      source.connect(proc);
      proc.connect(ctx.destination);
      startRecording();
    } catch (e) { micBlocked(); }
  }

  // AudioWorklet is present here: a module or node that fails is shown in the panel, never replaced by the fallback.
  function useWorklet() {
    try {
      node = new AudioWorkletNode(ctx, "agentimo-recorder", { numberOfInputs: 1, numberOfOutputs: 1, channelCount: 1 });
      node.port.onmessage = function (e) { onSamples(e.data); };
      source.connect(node);
      node.connect(ctx.destination);
      startRecording();
    } catch (e) { micBlocked(); }
  }

  function attach(s) {
    stream = s;
    source = ctx.createMediaStreamSource(s);
    if (ctx.audioWorklet && typeof AudioWorkletNode === "function") {
      ctx.audioWorklet.addModule(WORKLET_URL).then(useWorklet, micBlocked);
    } else { useScriptProcessor(); }
  }

  // Inside the tap, before the microphone is asked for: iOS leaves a context made later suspended.
  function prepareAudio() {
    var AC = window.AudioContext || window.webkitAudioContext;
    if (!ctx && AC) {
      try { ctx = new AC(); } catch (e) { ctx = null; }
    }
    if (ctx && ctx.state !== "running" && ctx.resume) {
      var resumed = ctx.resume();
      if (resumed && resumed.catch) { resumed.catch(function () {}); }
    }
  }

  function listen(fromTap) {
    if (busy || listening || panel.hidden) { return; }
    if (stream && ctx) { startRecording(); return; }
    if (!ctx) { if (fromTap) { micBlocked(); } else { tapToAnswer(); } return; }
    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) { micBlocked(); return; }
    navigator.mediaDevices.getUserMedia({ audio: true }).then(attach, micBlocked);
  }

  function onFalar() {
    openPanel();
    setBackdrop(true);
    if (panel.getAttribute("data-needs-settings") === "1") { showSettingsFirst(); return; }
    if (listening) { finishListening(true); return; }
    stopSpeech();
    prepareAudio();
    listen(true);
  }

  fab.addEventListener("click", onFalar);
  if (hdr) { hdr.addEventListener("click", onFalar); }

  form.addEventListener("submit", function (e) {
    e.preventDefault();
    var text = input.value.trim();
    if (!text || busy) { return; }
    input.value = "";
    sendText(text);
  });

  confirmBtn.addEventListener("click", function () {
    if (busy) { return; }
    stopSpeech(); finishListening(false);
    setBusy(true);
    post("/voice/confirm", { conversation_id: convId.value }).then(render, failed);
  });

  cancelBtn.addEventListener("click", function () {
    stopSpeech(); finishListening(false);
    setBusy(true);
    post("/voice/cancel", { conversation_id: convId.value }).then(render, failed);
  });
})();
