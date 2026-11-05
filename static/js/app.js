/* KrishiMitra premium dashboard logic.
   Same-origin relative fetch only. No secrets, no external hosts,
   no invented data: every number shown comes from the backend. */
"use strict";

(function () {
  var I18N = window.KM_I18N;
  var VIEWS = ["dashboard", "chat", "image", "voice", "weather", "mandi", "plan", "register"];
  var MAX_BYTES = 10 * 1024 * 1024;
  var IMAGE_EXTS = [".jpg", ".jpeg", ".png", ".webp"];
  var AUDIO_EXTS = [".mp3", ".wav", ".m4a", ".ogg", ".webm"];

  /* Last crop-scan result of this session (shown on the dashboard).
     Never persisted, never invented: only what /image/analyse returned. */
  window.KM_LAST_SCAN = null;

  /* ---------- storage ---------- */

  function storeGet(key) {
    try { return window.localStorage.getItem(key); } catch (e) { return null; }
  }
  function storeSet(key, value) {
    try { window.localStorage.setItem(key, value); } catch (e) { /* private mode */ }
  }
  function lang() { return I18N.validLang(storeGet("km_lang") || "en"); }
  function t(key) { return I18N.get(lang(), key); }
  function farmerId() {
    var raw = (storeGet("km_farmer_id") || "").trim();
    var id = parseInt(raw, 10);
    return id > 0 ? id : null;
  }

  /* ---------- helpers ---------- */

  function esc(value) {
    return String(value === null || value === undefined ? "" : value)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function $(id) { return document.getElementById(id); }

  /* Fetch helper: relative same-origin URLs only. Absolute URLs are
     refused so the page can never send data elsewhere. */
  async function api(path, options) {
    if (!path || path.charAt(0) !== "/" || /^\/\/|https?:/i.test(path)) {
      throw new Error("Only relative same-origin URLs are allowed.");
    }
    var resp;
    try {
      resp = await fetch(path, options);
    } catch (e) {
      throw new Error(t("common_network"));
    }
    var body = null;
    try { body = await resp.json(); } catch (e) { body = null; }
    if (!resp.ok) {
      var detail = body && (body.detail || body.note)
        ? (body.detail || body.note)
        : ("HTTP " + resp.status);
      var err = new Error(detail);
      err.status = resp.status;
      throw err;
    }
    if (body === null) throw new Error(t("common_no_result"));
    return body;
  }

  function slots(root) {
    var scope = root || document;
    return {
      loading: scope.querySelector("[data-slot-loading]"),
      error: scope.querySelector("[data-slot-error]"),
      result: scope.querySelector("[data-slot-result]")
    };
  }

  function showLoading(el, on) {
    if (!el) return;
    el.hidden = !on;
    if (on) el.textContent = t("common_loading");
  }

  function showError(el, message) {
    if (!el) return;
    if (!message) { el.hidden = true; el.textContent = ""; return; }
    el.hidden = false;
    el.textContent = message;
  }

  function showResult(el, html) {
    if (!el) return;
    el.hidden = false;
    el.innerHTML = html; /* values escaped via esc() at build time */
  }

  function skeletonHtml(lines) {
    var out = "";
    for (var i = 0; i < (lines || 3); i++) out += '<div class="km-skeleton"></div>';
    return out;
  }

  function fmt(value, suffix) {
    if (value === null || value === undefined || value === "") return "-";
    return esc(value) + (suffix ? esc(suffix) : "");
  }

  function unavailableHtml(message) {
    return "<p><strong>" + esc(message) + "</strong></p>" +
      "<p class=\"km-muted\">" + esc(t("common_local_check")) + "</p>";
  }

  function needFarmerHtml() {
    return "<p>" + esc(t("dash_no_farmer")) + "</p>" +
      '<p><button type="button" class="km-btn secondary" data-goto="register">' +
      esc(t("nav_register")) + "</button></p>";
  }

  function confidenceBadge(value) {
    if (!value) return "";
    var cls = value === "low" ? "km-badge low" : "km-badge";
    return '<span class="' + cls + '">' + esc(t("image_confidence")) +
      ": " + esc(value) + "</span>";
  }

  function listHtml(items, ordered) {
    if (!items || !items.length) return "";
    var tag = ordered ? "ol" : "ul";
    var cls = ordered ? "km-list ordered" : "km-list";
    return "<" + tag + ' class="' + cls + '">' + items.map(function (x) {
      return "<li>" + esc(x) + "</li>";
    }).join("") + "</" + tag + ">";
  }

  function checkFile(file, allowedExts) {
    if (!file || !file.name) return t("common_required");
    var name = file.name.toLowerCase();
    var ok = allowedExts.some(function (ext) { return name.endsWith(ext); });
    if (!ok) return t("common_file_type") + allowedExts.join(", ");
    if (file.size > MAX_BYTES) return t("common_file_size");
    if (file.size === 0) return t("common_required");
    return "";
  }

  /* ---------- language ---------- */

  function applyLang(value) {
    value = I18N.validLang(value);
    storeSet("km_lang", value);
    document.documentElement.lang = value;
    document.querySelectorAll("[data-lang-btn]").forEach(function (btn) {
      btn.setAttribute("aria-pressed", btn.dataset.langBtn === value ? "true" : "false");
    });
    document.querySelectorAll("[data-i18n]").forEach(function (el) {
      el.textContent = t(el.dataset.i18n);
    });
    document.querySelectorAll("[data-i18n-ph]").forEach(function (el) {
      el.setAttribute("placeholder", t(el.dataset.i18nPh));
    });
    document.querySelectorAll("[data-i18n-aria]").forEach(function (el) {
      el.setAttribute("aria-label", t(el.dataset.i18nAria));
    });
    updateFarmerChip();
  }

  function updateFarmerChip() {
    var chip = $("km-farmer-chip");
    if (!chip) return;
    var id = farmerId();
    if (id) {
      chip.dataset.empty = "false";
      chip.textContent = t("farmer_chip") + " #" + id;
    } else {
      chip.dataset.empty = "true";
      chip.textContent = t("farmer_none");
    }
  }

  /* ---------- view router ---------- */

  function showView(name) {
    if (VIEWS.indexOf(name) === -1) name = "dashboard";
    document.querySelectorAll(".km-view").forEach(function (sec) {
      sec.dataset.active = sec.id === "view-" + name ? "true" : "false";
    });
    document.querySelectorAll("[data-view-btn]").forEach(function (btn) {
      if (btn.dataset.viewBtn === name) btn.setAttribute("aria-current", "page");
      else btn.removeAttribute("aria-current");
    });
    if (("location" in window) && window.location.hash !== "#" + name) {
      try { window.history.replaceState(null, "", "#" + name); } catch (e) { /* ignore */ }
    }
    if (name === "dashboard") loadDashboard();
    if (name === "chat") loadChatHistory();
    window.scrollTo(0, 0);
  }

  /* ---------- dashboard ---------- */

  var dashLoaded = false;

  function loadDashboard() {
    dashProfile();
    dashWeather();
    dashCrop();
    dashMandi();
    dashRecent();
    dashReco();
    dashServices();
    dashLoaded = true;
  }

  function dashServices() {
    var box = $("dash-services");
    if (!box) return;
    box.innerHTML = skeletonHtml(2);
    api("/whatsapp/status").then(function (w) {
      api("/ai/status").then(function (a) {
        var wa = (w && w.configured) ? t("svc_ready") : t("svc_not_connected");
        var ai = (a && a.mode === "real") ? t("svc_ready") : t("svc_not_connected");
        box.innerHTML = "<dl class=\"km-kv\">" +
          "<div><dt>" + esc(t("svc_whatsapp")) + "</dt><dd>" + esc(wa) + "</dd></div>" +
          "<div><dt>" + esc(t("svc_ai")) + "</dt><dd>" + esc(ai) + "</dd></div>" +
          "</dl>";
      }, function () {
        box.innerHTML = "<p class=\"km-muted\">" + esc(t("common_error")) + "</p>";
      });
    }, function () {
      box.innerHTML = "<p class=\"km-muted\">" + esc(t("common_error")) + "</p>";
    });
  }

  function dashProfile() {
    var box = $("dash-profile");
    if (!box) return;
    var id = farmerId();
    if (!id) { box.innerHTML = needFarmerHtml(); return; }
    box.innerHTML = skeletonHtml(3);
    api("/farmers/" + id).then(function (f) {
      var place = [f.village, f.district].filter(Boolean).join(", ");
      box.innerHTML =
        "<p><strong>" + esc(f.name) + "</strong> (#" + esc(f.id) + ")</p>" +
        "<dl class=\"km-kv\">" +
        "<div><dt>" + esc(t("reg_phone")) + "</dt><dd>" + esc(f.phone) + "</dd></div>" +
        (place ? "<div><dt>" + esc(t("reg_village")) + "</dt><dd>" + esc(place) + "</dd></div>" : "") +
        "</dl>";
    }, function (err) {
      box.innerHTML = "<p><strong>" + esc(err.message || t("common_error")) + "</strong></p>";
    });
  }

  function dashWeather() {
    var box = $("dash-weather");
    if (!box) return;
    var city = (storeGet("km_city") || "Madurai").trim() || "Madurai";
    box.innerHTML = skeletonHtml(2);
    var params = new URLSearchParams({ city: city, language: lang() });
    api("/weather?" + params.toString()).then(function (w) {
      if (!w || w.status !== "ok") {
        box.innerHTML = unavailableHtml(t("weather_unavailable"));
        return;
      }
      box.innerHTML =
        "<p><strong>" + esc(w.resolved_name || w.location || city) + "</strong></p>" +
        "<div class=\"km-stats\">" +
        "<div class=\"km-stat\"><strong>" + fmt(w.temperature_c, " °C") + "</strong><span>" +
        esc(t("weather_temp")) + "</span></div>" +
        "<div class=\"km-stat\"><strong>" + fmt(w.precipitation_mm, " mm") + "</strong><span>" +
        esc(t("weather_rain")) + "</span></div>" +
        "<div class=\"km-stat\"><strong>" + fmt(w.wind_kph, " kph") + "</strong><span>" +
        esc(t("weather_wind")) + "</span></div>" +
        "</div>" +
        (w.condition ? "<p class=\"km-muted\">" + esc(w.condition) + "</p>" : "");
    }, function () {
      box.innerHTML = unavailableHtml(t("weather_unavailable"));
    });
  }

  function dashCrop() {
    var box = $("dash-crop");
    if (!box) return;
    var scan = window.KM_LAST_SCAN;
    if (!scan) {
      box.innerHTML = "<p class=\"km-muted\">" + esc(t("dash_no_scan")) + "</p>" +
        '<p><button type="button" class="km-btn secondary" data-goto="image">' +
        esc(t("dash_open_scan")) + "</button></p>";
      return;
    }
    box.innerHTML =
      "<p>" + confidenceBadge(scan.confidence) + "</p>" +
      "<p>" + esc(scan.observation || "-") + "</p>" +
      (scan.safety_note ? "<p class=\"km-muted\">" + esc(scan.safety_note) + "</p>" : "");
  }

  function dashMandi() {
    var box = $("dash-mandi");
    if (!box) return;
    var crop = (storeGet("km_crop") || "Tomato").trim() || "Tomato";
    var market = (storeGet("km_market") || "").trim();
    box.innerHTML = skeletonHtml(2);
    var params = new URLSearchParams({ crop: crop });
    if (market) params.set("market", market);
    api("/mandi?" + params.toString()).then(function (m) {
      if (!m || m.status !== "ok" || m.modal_price === undefined) {
        box.innerHTML = unavailableHtml(t("mandi_unavailable"));
        return;
      }
      box.innerHTML =
        "<p><strong>" + esc(m.commodity || crop) + "</strong></p>" +
        "<div class=\"km-stats\">" +
        "<div class=\"km-stat\"><strong>Rs " + fmt(m.modal_price) + "</strong><span>" +
        esc(t("mandi_modal")) + " (" + esc(t("mandi_per_quintal")) + ")</span></div>" +
        "</div>";
    }, function () {
      box.innerHTML = unavailableHtml(t("mandi_unavailable"));
    });
  }

  function dashRecent() {
    var box = $("dash-recent");
    if (!box) return;
    var id = farmerId();
    if (!id) { box.innerHTML = needFarmerHtml(); return; }
    box.innerHTML = skeletonHtml(3);
    api("/farmers/" + id + "/conversations").then(function (rows) {
      if (!rows || !rows.length) {
        box.innerHTML = "<p class=\"km-muted\">" + esc(t("dash_no_chat")) + "</p>";
        return;
      }
      var last = rows.slice(-4).reverse();
      box.innerHTML = "<ul class=\"km-list\">" + last.map(function (m) {
        var who = m.role === "farmer" ? t("chat_you") : t("chat_assistant");
        var text = String(m.content || "");
        if (text.length > 90) text = text.slice(0, 90) + "...";
        return "<li><strong>" + esc(who) + ":</strong> " + esc(text) + "</li>";
      }).join("") + "</ul>";
    }, function (err) {
      box.innerHTML = "<p><strong>" + esc(err.message || t("common_error")) + "</strong></p>";
    });
  }

  function dashReco() {
    var box = $("dash-reco");
    if (!box) return;
    var id = farmerId();
    if (!id) { box.innerHTML = needFarmerHtml(); return; }
    box.innerHTML = skeletonHtml(3);
    api("/plan/" + id + "?language=" + lang()).then(function (p) {
      var steps = (p.immediate_steps || []).slice(0, 3);
      box.innerHTML = "<p>" + esc(p.summary || "") + "</p>" +
        listHtml(steps, true) +
        '<p><button type="button" class="km-btn secondary" data-goto="plan">' +
        esc(t("dash_open_plan")) + "</button></p>";
    }, function (err) {
      box.innerHTML = "<p><strong>" + esc(err.message || t("common_error")) + "</strong></p>";
    });
  }

  /* ---------- AI chat (conversations API with AI reply) ---------- */

  var chatLoadedFor = null;
  var chatSending = false;

  function chatLog() { return $("chat-log"); }

  function chatBubble(role, text) {
    var log = chatLog();
    if (!log) return;
    var who = role === "farmer" ? t("chat_you") : t("chat_assistant");
    var div = document.createElement("div");
    div.className = "km-msg " + (role === "farmer" ? "farmer" : "assistant");
    var whoEl = document.createElement("span");
    whoEl.className = "km-who";
    whoEl.textContent = who;
    var p = document.createElement("p");
    p.textContent = text;
    div.appendChild(whoEl);
    div.appendChild(p);
    log.appendChild(div);
    log.scrollTop = log.scrollHeight;
  }

  function chatTyping(on) {
    var log = chatLog();
    if (!log) return;
    var old = $("chat-typing");
    if (old) old.remove();
    if (!on) return;
    var div = document.createElement("div");
    div.className = "km-msg assistant";
    div.id = "chat-typing";
    div.setAttribute("aria-live", "polite");
    div.innerHTML = '<span class="km-who">' + esc(t("chat_assistant")) + "</span>" +
      '<span class="km-typing" aria-label="' + esc(t("chat_typing")) +
      '"><i></i><i></i><i></i></span>';
    log.appendChild(div);
    log.scrollTop = log.scrollHeight;
  }

  function loadChatHistory() {
    var log = chatLog();
    if (!log) return;
    var id = farmerId();
    if (!id) {
      log.innerHTML = "";
      var s = slots($("view-chat"));
      showError(s.error, t("chat_need_farmer"));
      return;
    }
    if (chatLoadedFor === id + ":" + lang()) return;
    chatLoadedFor = id + ":" + lang();
    var s2 = slots($("view-chat"));
    showError(s2.error, "");
    showLoading(s2.loading, true);
    api("/farmers/" + id + "/conversations").then(function (rows) {
      log.innerHTML = "";
      (rows || []).slice(-30).forEach(function (m) {
        if (m.role === "farmer" || m.role === "assistant") chatBubble(m.role, m.content || "");
      });
    }, function (err) {
      showError(s2.error, friendlyChatError(err));
    }).then(function () {
      showLoading(s2.loading, false);
    });
  }

  function friendlyChatError(err) {
    if (err && err.status === 404) return t("chat_need_farmer");
    if (err && err.status === 422) return t("chat_empty");
    return (err && err.message) || t("common_network");
  }

  function sendChat(message) {
    var text = (message || "").trim();
    var s = slots($("view-chat"));
    showError(s.error, "");
    if (!text) { showError(s.error, t("chat_empty")); return; }
    var id = farmerId();
    if (!id) { showError(s.error, t("chat_need_farmer")); return; }
    if (chatSending) return;
    chatSending = true;
    chatBubble("farmer", text);
    chatTyping(true);
    /* Exact contract: role "farmer" (never "user"), message_type text,
       ai_reply=true with a valid ai_language (never empty). */
    var url = "/farmers/" + id + "/conversations?ai_reply=true&ai_language=" + lang();
    api(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        role: "farmer",
        content: text,
        message_type: "text",
        language: lang()
      })
    }).then(function (reply) {
      chatTyping(false);
      chatBubble("assistant", (reply && reply.content) || t("common_no_result"));
      chatLoadedFor = null; /* history grew; reload next visit */
    }, function (err) {
      chatTyping(false);
      showError(s.error, friendlyChatError(err));
    }).then(function () {
      chatSending = false;
    });
  }

  /* ---------- crop image scan ---------- */

  var scanFile = null;

  function renderScanResult(ans) {
    /* Shows ONLY backend fields. Never claims a confirmed disease,
       never invents any treatment or dose. */
    var html = "<dl class=\"km-kv\">" +
      "<div><dt>" + esc(t("image_filename")) + "</dt><dd>" + fmt(ans.filename) + "</dd></div>" +
      "<div><dt>" + esc(t("image_mode")) + "</dt><dd>" + fmt(ans.mode) + "</dd></div>" +
      "</dl>" +
      "<p><strong>" + esc(t("image_observation")) + ":</strong> " +
      esc(ans.observation || "-") + "</p>";
    if (ans.possible_issues && ans.possible_issues.length) {
      html += "<p><strong>" + esc(t("image_possible")) + ":</strong></p>" +
        listHtml(ans.possible_issues);
    }
    html += "<p>" + confidenceBadge(ans.confidence) + "</p>";
    if (ans.confidence === "low") {
      html += "<p class=\"km-error\" style=\"display:block\">" +
        esc(t("image_low_warn")) + "</p>";
    }
    if (ans.needs_clearer_photo) {
      html += "<p class=\"km-muted\">" + esc(t("image_clearer")) + "</p>";
    }
    if (ans.guidance) {
      html += "<p><strong>" + esc(t("image_guidance")) + ":</strong> " +
        esc(ans.guidance) + "</p>";
    }
    if (ans.safety_note) {
      html += "<p class=\"km-safety\"><strong>" + esc(t("image_safety")) +
        ":</strong> " + esc(ans.safety_note) + "</p>";
    }
    return html;
  }

  function setScanFile(file) {
    var s = slots($("view-image"));
    var problem = checkFile(file, IMAGE_EXTS);
    if (problem) {
      scanFile = null;
      showError(s.error, problem);
      var prev = $("scan-preview");
      if (prev) prev.hidden = true;
      return;
    }
    scanFile = file;
    showError(s.error, "");
    var img = $("scan-preview");
    if (img) {
      if (img.src && img.src.indexOf("blob:") === 0) {
        try { URL.revokeObjectURL(img.src); } catch (e) { /* ignore */ }
      }
      img.src = URL.createObjectURL(file);
      img.hidden = false;
    }
  }

  function analyseScan() {
    var s = slots($("view-image"));
    showError(s.error, "");
    if (!scanFile) { showError(s.error, t("common_required")); return; }
    var body = new FormData();
    body.append("file", scanFile);
    body.append("language", lang());
    showLoading(s.loading, true);
    api("/image/analyse", { method: "POST", body: body }).then(function (ans) {
      window.KM_LAST_SCAN = ans; /* dashboard crop-health card reads this */
      dashCrop();
      showResult(s.result, renderScanResult(ans));
    }, function (err) {
      showError(s.error, (err && err.message) || t("common_network"));
    }).then(function () {
      showLoading(s.loading, false);
    });
  }

  /* ---------- voice ---------- */

  var recorder = null;
  var recChunks = [];
  var recording = false;
  var lastTranscript = "";

  function voiceSupported() {
    return !!(window.MediaRecorder && window.navigator &&
      window.navigator.mediaDevices && window.navigator.mediaDevices.getUserMedia);
  }

  async function toggleRecording() {
    var s = slots($("view-voice"));
    var btn = $("mic-btn");
    var status = $("mic-status");
    showError(s.error, "");
    if (recording) {
      try { recorder.stop(); } catch (e) { showError(s.error, t("common_error")); }
      return;
    }
    if (!voiceSupported()) { showError(s.error, t("voice_nomic")); return; }
    try {
      var stream = await window.navigator.mediaDevices.getUserMedia({ audio: true });
    } catch (e) {
      showError(s.error, t("voice_nomic"));
      return;
    }
    recChunks = [];
    try {
      recorder = new MediaRecorder(stream);
    } catch (e) {
      showError(s.error, t("voice_nomic"));
      return;
    }
    recorder.ondataavailable = function (ev) {
      if (ev.data && ev.data.size) recChunks.push(ev.data);
    };
    recorder.onstop = function () {
      recording = false;
      if (btn) {
        btn.dataset.recording = "false";
        btn.setAttribute("aria-label", t("voice_record"));
      }
      if (status) status.textContent = "";
      stream.getTracks().forEach(function (tr) { try { tr.stop(); } catch (e) {} });
      var blob = new Blob(recChunks, { type: recorder.mimeType || "audio/webm" });
      var file = new File([blob], "recording.webm", { type: "audio/webm" });
      transcribeFile(file);
    };
    recording = true;
    if (btn) {
      btn.dataset.recording = "true";
      btn.setAttribute("aria-label", t("voice_stop"));
    }
    if (status) {
      status.innerHTML = '<span class="km-rec-dot"></span>' + esc(t("voice_recording"));
    }
    recorder.start();
  }

  function transcribeFile(file) {
    var s = slots($("view-voice"));
    showError(s.error, "");
    var problem = checkFile(file, AUDIO_EXTS);
    if (problem) { showError(s.error, problem); return; }
    var body = new FormData();
    body.append("file", file);
    body.append("language", lang());
    showLoading(s.loading, true);
    api("/voice/transcribe", { method: "POST", body: body }).then(function (ans) {
      lastTranscript = (ans && ans.transcript) || "";
      var html = "<p><strong>" + esc(t("voice_transcript")) + ":</strong></p>" +
        "<p>" + esc(lastTranscript || "-") + "</p>";
      if (ans && ans.mode) {
        html += "<p class=\"km-muted\">" + esc(t("image_mode")) + ": " + esc(ans.mode) + "</p>";
      }
      if (lastTranscript) {
        html += '<p><button type="button" class="km-btn secondary" id="voice-to-chat">' +
          esc(t("voice_send_chat")) + "</button></p>";
      }
      showResult(s.result, html);
      var go = $("voice-to-chat");
      if (go) go.addEventListener("click", sendTranscriptToChat);
    }, function (err) {
      showError(s.error, (err && err.message) || t("common_network"));
    }).then(function () {
      showLoading(s.loading, false);
    });
  }

  function sendTranscriptToChat() {
    if (!lastTranscript) return;
    var input = $("chat-input");
    showView("chat");
    if (input) {
      input.value = lastTranscript;
      input.focus();
    }
    var s = slots($("view-chat"));
    showError(s.error, "");
  }

  /* ---------- weather ---------- */

  function renderWeather(w) {
    if (!w || w.status !== "ok") return unavailableHtml(w && w.note ? w.note : t("weather_unavailable"));
    var html = "<p><strong>" + esc(w.resolved_name || w.location || "-") + "</strong>" +
      (w.country ? " (" + esc(w.country) + ")" : "") + "</p>" +
      "<div class=\"km-stats\">" +
      "<div class=\"km-stat\"><strong>" + fmt(w.temperature_c, " °C") + "</strong><span>" +
      esc(t("weather_temp")) + "</span></div>" +
      "<div class=\"km-stat\"><strong>" + fmt(w.feels_like_c, " °C") + "</strong><span>" +
      esc(t("weather_feels")) + "</span></div>" +
      "<div class=\"km-stat\"><strong>" + fmt(w.precipitation_mm, " mm") + "</strong><span>" +
      esc(t("weather_rain")) + "</span></div>" +
      "<div class=\"km-stat\"><strong>" + fmt(w.humidity_pct, " %") + "</strong><span>" +
      esc(t("weather_humidity")) + "</span></div>" +
      "<div class=\"km-stat\"><strong>" + fmt(w.wind_kph, " kph") + "</strong><span>" +
      esc(t("weather_wind")) + "</span></div>" +
      "</div>";
    if (w.condition) {
      html += "<p>" + esc(t("weather_condition")) + ": <strong>" + esc(w.condition) + "</strong></p>";
    }
    /* Alerts only if the backend ever returns them; never invented. */
    if (w.alerts && w.alerts.length) {
      html += "<p><strong>Alerts:</strong></p>" + listHtml(w.alerts);
    }
    if (w.daily && w.daily.length) {
      html += "<p><strong>" + esc(t("weather_next")) + ":</strong></p><ul class=\"km-list\">" +
        w.daily.slice(0, 5).map(function (d) {
          return "<li>" + esc(d.date || "-") + ": " +
            fmt(d.temp_min_c, "°") + "–" + fmt(d.temp_max_c, "°C") + ", " +
            esc(t("weather_rain")) + " " + fmt(d.rain_mm, " mm") + "</li>";
        }).join("") + "</ul>";
    }
    if (w.guidance) {
      html += "<p><strong>" + esc(t("weather_guidance")) + ":</strong> " + esc(w.guidance) + "</p>";
    }
    html += "<p class=\"km-muted\">" + esc(t("weather_source")) + ": " +
      fmt(w.source) + " · " + esc(t("weather_updated")) + ": " +
      fmt(w.fetched_at || w.timestamp) + "</p>";
    return html;
  }

  function fetchWeather() {
    var s = slots($("view-weather"));
    showError(s.error, "");
    var city = ($("weather-city").value || "").trim();
    var lat = ($("weather-lat").value || "").trim();
    var lon = ($("weather-lon").value || "").trim();
    var params = new URLSearchParams({ language: lang() });
    if (lat !== "" || lon !== "") {
      if (lat === "" || lon === "") { showError(s.error, t("common_required")); return; }
      params.set("lat", lat);
      params.set("lon", lon);
    } else if (city) {
      params.set("city", city);
      storeSet("km_city", city);
    } else {
      showError(s.error, t("common_required"));
      return;
    }
    showLoading(s.loading, true);
    api("/weather?" + params.toString()).then(function (w) {
      showResult(s.result, renderWeather(w));
      dashWeather();
    }, function (err) {
      showError(s.error, (err && err.message) || t("common_network"));
    }).then(function () {
      showLoading(s.loading, false);
    });
  }

  /* ---------- mandi ---------- */

  function renderMandi(m, crop) {
    if (!m || m.status !== "ok" || m.modal_price === undefined) {
      return unavailableHtml(m && m.note ? m.note : t("mandi_unavailable"));
    }
    var html = "<p><strong>" + esc(m.commodity || crop) + " - " +
      esc(m.market || "-") + "</strong></p>" +
      "<div class=\"km-stats\">" +
      "<div class=\"km-stat\"><strong>Rs " + fmt(m.modal_price) + "</strong><span>" +
      esc(t("mandi_modal")) + " (" + esc(t("mandi_per_quintal")) + ")</span></div>" +
      "</div>" +
      "<dl class=\"km-kv\">" +
      ((m.min_price !== undefined && m.max_price !== undefined)
        ? "<div><dt>" + esc(t("mandi_range")) + "</dt><dd>Rs " + fmt(m.min_price) +
          " - Rs " + fmt(m.max_price) + "</dd></div>"
        : "") +
      (m.district ? "<div><dt>District</dt><dd>" + esc(m.district) + "</dd></div>" : "") +
      (m.state ? "<div><dt>State</dt><dd>" + esc(m.state) + "</dd></div>" : "") +
      "<div><dt>" + esc(t("mandi_date")) + "</dt><dd>" + fmt(m.arrival_date) + "</dd></div>" +
      "<div><dt>" + esc(t("mandi_source")) + "</dt><dd>" + fmt(m.source) + "</dd></div>" +
      "</dl>";
    /* Chart ONLY when the backend returns a history array; otherwise hidden. */
    if (m.history && Array.isArray(m.history) && m.history.length) {
      var rows = m.history.filter(function (h) {
        return h && h.modal_price !== undefined && h.modal_price !== null;
      });
      if (rows.length) {
        var max = rows.reduce(function (a, h) {
          return Math.max(a, Number(h.modal_price) || 0);
        }, 0) || 1;
        html += "<p><strong>" + esc(t("mandi_history")) + ":</strong></p>" +
          '<div class="km-bars">' + rows.slice(0, 10).map(function (h) {
            var pct = Math.max(2, Math.round((Number(h.modal_price) || 0) / max * 100));
            return '<div class="km-bar-row"><span>' + esc(h.arrival_date || h.date || "") +
              "</span>" + '<span class="km-bar-track"><span class="km-bar-fill" style="display:block;width:' +
              pct + '%"></span></span><span>Rs ' + esc(h.modal_price) + "</span></div>";
          }).join("") + "</div>";
      }
    }
    return html;
  }

  function fetchMandi() {
    var s = slots($("view-mandi"));
    showError(s.error, "");
    var crop = ($("mandi-crop").value || "").trim();
    var market = ($("mandi-market").value || "").trim();
    if (!crop) { showError(s.error, t("common_required")); return; }
    storeSet("km_crop", crop);
    storeSet("km_market", market);
    var params = new URLSearchParams({ crop: crop });
    if (market) params.set("market", market);
    showLoading(s.loading, true);
    api("/mandi?" + params.toString()).then(function (m) {
      showResult(s.result, renderMandi(m, crop));
      dashMandi();
    }, function (err) {
      showError(s.error, (err && err.message) || t("common_network"));
    }).then(function () {
      showLoading(s.loading, false);
    });
  }

  /* ---------- rescue plan ---------- */

  function planSection(title, bodyHtml) {
    if (!bodyHtml) return "";
    return '<div class="km-card" style="margin-top:0.8rem"><h3>' + esc(title) +
      "</h3>" + bodyHtml + "</div>";
  }

  function aiBadge(mode) {
    if (mode === "mock") return ' <span class="km-muted">(' + esc(t("rpt_ai_mock")) + ")</span>";
    if (mode === "fallback") return ' <span class="km-muted">(' + esc(t("rpt_ai_fallback")) + ")</span>";
    return "";
  }

  function renderAiPlan(ap, mode) {
    var title = esc(t("rpt_ai")) + aiBadge(mode);
    var head = "<p><strong>" + esc(ap.detected_issue || "-") + "</strong> " +
      confidenceBadge(ap.confidence) + "</p>" +
      "<p>" + esc(ap.explanation || "-") + "</p>";
    var html = planSection(title, head);
    html += planSection(t("aiplan_causes"), listHtml(ap.possible_causes));
    html += planSection(t("aiplan_organic"), listHtml(ap.organic_treatment, true));
    html += planSection(t("aiplan_actions"), listHtml(ap.recommended_actions, true));
    html += planSection(t("aiplan_prevent"), listHtml(ap.prevention_tips));
    html += planSection(t("aiplan_expert"), "<p>" + esc(ap.expert_referral || "-") + "</p>");
    return html;
  }

  function renderPlan(p, id) {
    var html = "<h3>" + esc(p.title || t("plan_title")) + " " +
      confidenceBadge(p.confidence) + "</h3>" +
      "<p class=\"km-muted\">" + esc(p.farmer_name || "") +
      " · " + esc(p.crop_display || "") + " · " + esc(p.topic_display || "") + "</p>";
    html += planSection(t("plan_summary"), "<p>" + esc(p.summary || "-") + "</p>");
    html += planSection(t("plan_safe"), listHtml(p.immediate_steps, true));
    html += planSection(t("plan_prevent"), listHtml(p.watch_out_for));
    html += planSection(t("plan_followup"), listHtml(p.follow_up, true));
    html += planSection(t("plan_info"), listHtml(p.questions_for_expert));
    html += planSection(t("plan_expert"), "<p>" + esc(p.expert_referral || "-") + "</p>");
    if (p.ai_plan) {
      html += renderAiPlan(p.ai_plan, p.ai_mode);
    } else if (p.ai_guidance) {
      var aiTitle = esc(t("rpt_ai")) + aiBadge(p.ai_mode);
      html += planSection(aiTitle, "<p>" + esc(p.ai_guidance) + "</p>");
    }
    var safety = "";
    if (p.safety_note) safety += "<p>" + esc(p.safety_note) + "</p>";
    if (p.disclaimer) safety += "<p class=\"km-muted\">" + esc(p.disclaimer) + "</p>";
    html += planSection(t("plan_safety"), safety);
    var cardUrl = "/plan/" + id + "/card?language=" + lang();
    html += '<div class="km-btn-row">' +
      '<a class="km-btn secondary" href="' + esc(cardUrl) + '" target="_blank" rel="noopener">' +
      esc(t("plan_card")) + "</a>" +
      '<button type="button" class="km-btn ghost" id="plan-print">' +
      esc(t("plan_print")) + "</button>" +
      '<button type="button" class="km-btn ghost" id="plan-share">' +
      esc(t("plan_share")) + "</button></div>";
    return html;
  }

  function bindPlanButtons(id, s) {
    var printBtn = $("plan-print");
    if (printBtn) printBtn.addEventListener("click", function () {
      var w = window.open("/plan/" + id + "/card?language=" + lang(), "_blank");
      if (w) {
        try { w.addEventListener("load", function () { w.print(); }); } catch (e) { /* ignore */ }
      }
    });
    var shareBtn = $("plan-share");
    if (shareBtn) shareBtn.addEventListener("click", function () {
      var url = window.location.origin + "/plan/" + id + "/card?language=" + lang();
      if (window.navigator && window.navigator.share) {
        window.navigator.share({ title: document.title, url: url }).catch(function () { /* dismissed */ });
      } else if (window.navigator && window.navigator.clipboard) {
        window.navigator.clipboard.writeText(url).then(function () {
          showError(s.error, "");
          var note = document.createElement("p");
          note.className = "km-muted";
          note.textContent = t("plan_share_copied");
          s.result.appendChild(note);
        }, function () {
          showError(s.error, t("plan_share_fail"));
        });
      } else {
        showError(s.error, t("plan_share_fail"));
      }
    });
  }

  function fetchPlan() {
    var s = slots($("view-plan"));
    showError(s.error, "");
    var raw = ($("plan-farmer").value || "").trim() || String(farmerId() || "");
    var id = parseInt(raw, 10);
    if (!id || id <= 0) { showError(s.error, t("common_bad_id")); return; }
    showLoading(s.loading, true);
    api("/plan/" + id + "?language=" + lang()).then(function (p) {
      showResult(s.result, renderPlan(p, id));
      bindPlanButtons(id, s);
    }, function (err) {
      showError(s.error, (err && err.message) || t("common_network"));
    }).then(function () {
      showLoading(s.loading, false);
    });
  }

  function submitReport() {
    var card = $("rpt-card");
    var s = slots($("view-plan"));
    var loading = card ? card.querySelector("[data-rpt-loading]") : null;
    var errorEl = card ? card.querySelector("[data-rpt-error]") : null;
    showError(errorEl, "");
    showError(s.error, "");
    var raw = ($("plan-farmer").value || "").trim() || String(farmerId() || "");
    var id = parseInt(raw, 10);
    if (!id || id <= 0) { showError(errorEl, t("rpt_need_id")); return; }
    var crop = ($("rpt-crop").value || "").trim();
    var symptoms = ($("rpt-symptoms").value || "").trim();
    if (!crop || !symptoms) { showError(errorEl, t("common_required")); return; }
    var areaRaw = ($("rpt-area").value || "").trim();
    if (areaRaw) {
      var area = Number(areaRaw);
      if (!isFinite(area) || area < 0 || area > 100) {
        showError(errorEl, t("rpt_bad_area")); return;
      }
    }
    var daysRaw = ($("rpt-days").value || "").trim();
    if (daysRaw && (!/^\d+$/.test(daysRaw) || parseInt(daysRaw, 10) > 365)) {
      showError(errorEl, t("rpt_bad_days")); return;
    }
    var photoInput = $("rpt-photo");
    var photo = photoInput && photoInput.files ? photoInput.files[0] : null;
    if (photo) {
      var ext = "." + (photo.name.split(".").pop() || "").toLowerCase();
      if (IMAGE_EXTS.indexOf(ext) < 0) {
        showError(errorEl, t("common_file_type") + IMAGE_EXTS.join(", ")); return;
      }
      if (photo.size > MAX_BYTES) { showError(errorEl, t("common_file_size")); return; }
    }
    var body = new FormData();
    body.append("crop_name", crop);
    body.append("symptoms", symptoms);
    var stage = ($("rpt-stage").value || "").trim();
    if (stage) body.append("growth_stage", stage);
    if (areaRaw) body.append("affected_area_pct", areaRaw);
    if (daysRaw) body.append("days_affected", daysRaw);
    var soil = ($("rpt-soil").value || "").trim();
    if (soil) body.append("soil_type", soil);
    var water = ($("rpt-water").value || "").trim();
    if (water) body.append("irrigation_method", water);
    var loc = ($("rpt-location").value || "").trim();
    if (loc) body.append("location", loc);
    var wx = ($("rpt-weather").value || "").trim();
    if (wx) body.append("recent_weather", wx);
    if (photo) body.append("file", photo);
    showLoading(loading, true);
    api("/plan/" + id + "/report?language=" + lang(), { method: "POST", body: body }).then(function (ans) {
      showResult(s.result, renderPlan(ans.plan || {}, id));
      bindPlanButtons(id, s);
    }, function (err) {
      showError(errorEl, (err && err.message) || t("common_network"));
    }).then(function () {
      showLoading(loading, false);
    });
  }

  /* ---------- register ---------- */

  function registerFarmer() {
    var s = slots($("view-register"));
    showError(s.error, "");
    var name = ($("reg-name").value || "").trim();
    var phone = ($("reg-phone").value || "").trim();
    var village = ($("reg-village").value || "").trim();
    var district = ($("reg-district").value || "").trim();
    var pref = ($("reg-lang").value || lang());
    if (!name || !phone) { showError(s.error, t("common_required")); return; }
    showLoading(s.loading, true);
    /* Schema field is preferred_language; plain "language" is also sent
       for compatibility and ignored by the backend otherwise. */
    var payload = { name: name, phone: phone, preferred_language: pref, language: pref };
    if (village) payload.village = village;
    if (district) payload.district = district;
    api("/farmers/", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    }).then(function (created) {
      storeSet("km_farmer_id", String(created.id));
      storeSet("km_lang", pref);
      applyLang(pref);
      chatLoadedFor = null;
      var planInput = $("plan-farmer");
      if (planInput) planInput.value = String(created.id);
      showResult(s.result,
        "<p><strong>" + esc(t("reg_done")) + " " + esc(created.id) + "</strong></p>" +
        "<p>" + esc(created.name) + " | " + esc(created.phone) + "</p>" +
        "<p class=\"km-muted\">" + esc(t("reg_saved")) + "</p>");
      loadDashboard();
    }, function (err) {
      if (err && err.status === 400) showError(s.error, t("reg_dup"));
      else showError(s.error, (err && err.message) || t("common_network"));
    }).then(function () {
      showLoading(s.loading, false);
    });
  }

  /* ---------- boot ---------- */

  document.addEventListener("DOMContentLoaded", function () {
    document.querySelectorAll("[data-lang-btn]").forEach(function (btn) {
      btn.addEventListener("click", function () {
        applyLang(btn.dataset.langBtn);
        chatLoadedFor = null;
        loadDashboard();
        var active = document.querySelector(".km-view[data-active=\"true\"]");
        if (active && active.id === "view-chat") loadChatHistory();
      });
    });
    applyLang(lang());

    document.querySelectorAll("[data-view-btn]").forEach(function (btn) {
      btn.addEventListener("click", function () { showView(btn.dataset.viewBtn); });
    });
    document.addEventListener("click", function (ev) {
      var go = ev.target && ev.target.closest ? ev.target.closest("[data-goto]") : null;
      if (go) showView(go.dataset.goto);
    });

    var start = (window.location.hash || "").replace("#", "");
    showView(VIEWS.indexOf(start) === -1 ? "dashboard" : start);

    var chatForm = $("chat-form");
    if (chatForm) chatForm.addEventListener("submit", function (ev) {
      ev.preventDefault();
      var input = $("chat-input");
      sendChat(input.value);
      input.value = "";
      input.focus();
    });

    var drop = $("scan-drop");
    var fileInput = $("scan-file");
    if (drop && fileInput) {
      drop.addEventListener("click", function () { fileInput.click(); });
      drop.addEventListener("keydown", function (ev) {
        if (ev.key === "Enter" || ev.key === " ") fileInput.click();
      });
      fileInput.addEventListener("change", function () {
        if (fileInput.files && fileInput.files[0]) setScanFile(fileInput.files[0]);
      });
      ["dragenter", "dragover"].forEach(function (name) {
        drop.addEventListener(name, function (ev) {
          ev.preventDefault();
          drop.dataset.drag = "true";
        });
      });
      ["dragleave", "drop"].forEach(function (name) {
        drop.addEventListener(name, function (ev) {
          ev.preventDefault();
          drop.dataset.drag = "false";
        });
      });
      drop.addEventListener("drop", function (ev) {
        var f = ev.dataTransfer && ev.dataTransfer.files ? ev.dataTransfer.files[0] : null;
        if (f) setScanFile(f);
      });
    }
    var scanBtn = $("scan-btn");
    if (scanBtn) scanBtn.addEventListener("click", analyseScan);

    var mic = $("mic-btn");
    if (mic) mic.addEventListener("click", toggleRecording);
    var voiceFile = $("voice-file");
    var voiceBtn = $("voice-btn");
    if (voiceBtn) voiceBtn.addEventListener("click", function () {
      var f = voiceFile && voiceFile.files ? voiceFile.files[0] : null;
      if (!f) {
        var s = slots($("view-voice"));
        showError(s.error, t("common_required"));
        return;
      }
      transcribeFile(f);
    });

    var weatherBtn = $("weather-btn");
    if (weatherBtn) weatherBtn.addEventListener("click", fetchWeather);
    var weatherCity = $("weather-city");
    if (weatherCity && !weatherCity.value) weatherCity.value = storeGet("km_city") || "Madurai";

    var mandiBtn = $("mandi-btn");
    if (mandiBtn) mandiBtn.addEventListener("click", fetchMandi);
    var mandiCrop = $("mandi-crop");
    if (mandiCrop && !mandiCrop.value) mandiCrop.value = storeGet("km_crop") || "Tomato";
    var mandiMarket = $("mandi-market");
    if (mandiMarket && !mandiMarket.value) mandiMarket.value = storeGet("km_market") || "";

    var planBtn = $("plan-btn");
    if (planBtn) planBtn.addEventListener("click", fetchPlan);
    var rptBtn = $("rpt-btn");
    if (rptBtn) rptBtn.addEventListener("click", submitReport);
    var planInput = $("plan-farmer");
    if (planInput && farmerId()) planInput.value = String(farmerId());

    var regBtn = $("reg-btn");
    if (regBtn) regBtn.addEventListener("click", registerFarmer);
    var regLang = $("reg-lang");
    if (regLang) regLang.value = lang();
  });
})();

