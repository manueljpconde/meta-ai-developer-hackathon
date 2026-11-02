(function () {
  "use strict";
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
  if (!panel || !form) { return; }
  var csrf = form.querySelector("input[name=csrf_token]").value;
  var TARGET_RATE = 16000;
  var MAX_SECONDS = 55;
  var SILENCE_SECONDS = 1.4;
  var NO_SPEECH_SECONDS = 10;
  var THRESHOLD = 0.02;

  var stream = null, ctx = null, source = null, proc = null;
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

  function downsample(samples, rate) {
    if (rate === TARGET_RATE) { return samples; }
    var ratio = rate / TARGET_RATE;
    var len = Math.floor(samples.length / ratio);
    var out = new Float32Array(len);
    for (var i = 0; i < len; i++) {
      var start = Math.floor(i * ratio), end = Math.min(samples.length, Math.floor((i + 1) * ratio));
      var sum = 0, count = 0;
      for (var j = start; j < end; j++) { sum += samples[j]; count++; }
      out[i] = count ? sum / count : 0;
    }
    return out;
  }

  function merge() {
    var all = new Float32Array(total), off = 0;
    for (var i = 0; i < chunks.length; i++) { all.set(chunks[i], off); off += chunks[i].length; }
    return all;
  }

  function setText(el, text) { el.textContent = text || ""; }

  function openPanel() { panel.hidden = false; }

  function releaseMic() {
    listening = false;
    try { if (proc) { proc.disconnect(); proc.onaudioprocess = null; } } catch (e) {}
    try { if (source) { source.disconnect(); } } catch (e) {}
    try { if (stream) { stream.getTracks().forEach(function (t) { t.stop(); }); } } catch (e) {}
    try { if (ctx && ctx.close) { ctx.close(); } } catch (e) {}
    stream = ctx = source = proc = null;
  }

  function stopSpeech() {
    if (speakTimer) { clearTimeout(speakTimer); speakTimer = null; }
    try { if (window.speechSynthesis) { window.speechSynthesis.cancel(); } } catch (e) {}
  }

  function resetView() {
    setText(transcriptEl, ""); setText(questionEl, ""); setText(readbackEl, "");
    confirmBtn.hidden = true;
    convId.value = "";
  }

  function closePanel(reload) {
    stopSpeech(); releaseMic(); panel.hidden = true; resetView();
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
    }).then(function (r) { return r.json(); });
  }

  function failed() {
    busy = false;
    setText(questionEl, panel.getAttribute("data-network-error"));
  }

  function render(d) {
    busy = false;
    if (d.conversation_id !== undefined) { convId.value = d.conversation_id; }
    if (d.transcript !== undefined) { setText(transcriptEl, d.transcript); }
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
    stopSpeech(); finishListening(false);
    if (busy) { return; }
    busy = true;
    post("/voice/extract", { conversation_id: convId.value, text: text }).then(render, failed);
  }

  function sendAudio(wav) {
    busy = true;
    var url = "/voice/transcribe?csrf_token=" + encodeURIComponent(csrf) +
      "&format=json&conversation_id=" + encodeURIComponent(convId.value);
    fetch(url, {
      method: "POST", credentials: "same-origin",
      headers: { "Content-Type": "audio/wav" }, body: wav
    }).then(function (r) { return r.json(); }).then(render, failed);
  }

  function finishListening(send) {
    if (!listening) { return; }
    listening = false;
    if (send && total > 0) {
      var samples = downsample(merge(), ctx ? ctx.sampleRate : TARGET_RATE);
      chunks = []; total = 0;
      sendAudio(encodeWav(samples));
    } else {
      chunks = []; total = 0;
    }
  }

  function onAudio(e) {
    if (!listening) { return; }
    var data = new Float32Array(e.inputBuffer.getChannelData(0));
    chunks.push(data); total += data.length;
    var sum = 0;
    for (var i = 0; i < data.length; i++) { sum += data[i] * data[i]; }
    var rms = Math.sqrt(sum / data.length);
    var rate = ctx.sampleRate;
    if (rms > THRESHOLD) { speechSeen = true; silent = 0; } else { silent += data.length; }
    if (speechSeen && silent > SILENCE_SECONDS * rate) { finishListening(true); return; }
    if (total > MAX_SECONDS * rate) { finishListening(true); return; }
    if (!speechSeen && total > NO_SPEECH_SECONDS * rate) { finishListening(false); }
  }

  function startRecording() {
    chunks = []; total = 0; speechSeen = false; silent = 0; listening = true;
    if (ctx && ctx.state === "suspended" && ctx.resume) { ctx.resume(); }
  }

  function micBlocked() {
    releaseMic();
    setText(questionEl, panel.getAttribute("data-mic-blocked"));
  }

  function listen() {
    if (busy || listening || panel.hidden) { return; }
    if (stream && ctx) { startRecording(); return; }
    var AC = window.AudioContext || window.webkitAudioContext;
    if (!AC || !navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) { micBlocked(); return; }
    try { ctx = new AC(); } catch (e) { micBlocked(); return; }
    navigator.mediaDevices.getUserMedia({ audio: true }).then(function (s) {
      stream = s;
      source = ctx.createMediaStreamSource(s);
      proc = ctx.createScriptProcessor(4096, 1, 1);
      proc.onaudioprocess = onAudio;
      source.connect(proc);
      proc.connect(ctx.destination);
      startRecording();
    }, micBlocked);
  }

  function onFalar() {
    openPanel();
    if (listening) { finishListening(true); return; }
    stopSpeech();
    listen();
  }

  fab.addEventListener("click", onFalar);
  if (hdr) { hdr.addEventListener("click", onFalar); }

  form.addEventListener("submit", function (e) {
    e.preventDefault();
    var text = input.value.trim();
    if (!text) { return; }
    input.value = "";
    sendText(text);
  });

  confirmBtn.addEventListener("click", function () {
    stopSpeech(); finishListening(false);
    post("/voice/confirm", { conversation_id: convId.value }).then(render, failed);
  });

  cancelBtn.addEventListener("click", function () {
    stopSpeech(); finishListening(false);
    post("/voice/cancel", { conversation_id: convId.value }).then(render, failed);
  });
})();
