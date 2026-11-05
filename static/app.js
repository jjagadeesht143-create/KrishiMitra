/* KrishiMitra dashboard JS. Same-origin relative fetch only.
   No API keys, no secrets, no external hosts. Language en/ta/hi is
   saved on this device and sent with every API call. */
"use strict";

(function () {
  var LANGS = ["en", "ta", "hi"];

  var TEXT = {
    en: {
      loading: "Loading…",
      submit: "Register",
      send: "Send",
      errNetwork: "Could not reach the server. Check connection and retry.",
      errRequired: "Please fill the required field.",
      errBadId: "Farmer ID must be a number.",
      errFileType: "Wrong file type. Allowed: ",
      errFileSize: "File is larger than 10 MB.",
      errNoResult: "No answer received. Please retry.",
      checkPhoto: "Check photo",
      transcribe: "Transcribe",
      getWeather: "Get weather",
      getPrice: "Get price",
      getPlan: "Get my plan",
    },
    ta: {
      loading: "ஏற்றுகிறது…",
      submit: "பதிவு செய்",
      send: "அனுப்பு",
      errNetwork: "சேவையகத்தை அணுக முடியவில்லை. மீண்டும் முயலுங்கள்.",
      errRequired: "தேவையான இடத்தை நிரப்புங்கள்.",
      errBadId: "விவசாயி எண் இலக்கமாக இருக்க வேண்டும்.",
      errFileType: "தவறான கோப்பு வகை. அனுமதி: ",
      errFileSize: "கோப்பு 10 MB-க்கு மேல் உள்ளது.",
      errNoResult: "பதில் கிடைக்கவில்லை. மீண்டும் முயலுங்கள்.",
      checkPhoto: "படத்தை பார்",
      transcribe: "எழுத்தாக்கு",
      getWeather: "வானிலை பார்",
      getPrice: "விலை பார்",
      getPlan: "திட்டம் பார்",
    },
    hi: {
      loading: "लोड हो रहा है…",
      submit: "पंजीकरण करें",
      send: "भेजें",
      errNetwork: "सर्वर से संपर्क नहीं हुआ। फिर से कोशिश करें।",
      errRequired: "जरूरी जगह भरें।",
      errBadId: "किसान ID संख्या होनी चाहिए।",
      errFileType: "गलत फाइल प्रकार। अनुमति: ",
      errFileSize: "फाइल 10 MB से बड़ी है।",
      errNoResult: "जवाब नहीं मिला। फिर से कोशिश करें।",
      checkPhoto: "फोटो जांचें",
      transcribe: "लिखावट बनाएं",
      getWeather: "मौसम देखें",
      getPrice: "भाव देखें",
      getPlan: "योजना देखें",
    },
  };

  function lang() {
    try {
      var saved = window.localStorage.getItem("km_lang");
      if (LANGS.indexOf(saved) !== -1) return saved;
    } catch (e) { /* private mode: fall through */ }
    return "en";
  }

  function setLang(value) {
    if (LANGS.indexOf(value) === -1) value = "en";
    try { window.localStorage.setItem("km_lang", value); } catch (e) {}
    applyLang(value);
  }

  function t(key) {
    var pack = TEXT[lang()] || TEXT.en;
    return pack[key] || TEXT.en[key] || key;
  }

  function esc(value) {
    return String(value === null || value === undefined ? "" : value)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  /* Fetch helper: relative same-origin URLs only. Absolute http(s)
     URLs are refused so the page can never leak data elsewhere. */
  async function api(path, options) {
    if (!path || path.charAt(0) !== "/" || /^\/\/|https?:/i.test(path)) {
      throw new Error("Only relative same-origin URLs are allowed.");
    }
    var resp = await fetch(path, options);
    var body = null;
    try { body = await resp.json(); } catch (e) { body = null; }
    if (!resp.ok) {
      var detail = body && (body.detail || body.note) ? (body.detail || body.note) : ("HTTP " + resp.status);
      throw new Error(detail);
    }
    if (body === null) throw new Error(t("errNoResult"));
    return body;
  }

  function ui(root) {
    var scope = root || document;
    return {
      loading: scope.querySelector("[data-loading]"),
      error: scope.querySelector("[data-error]"),
      result: scope.querySelector("[data-result]"),
    };
  }

  function showLoading(el, on, label) {
    if (!el) return;
    el.hidden = !on;
    if (on) el.textContent = label || t("loading");
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
    el.innerHTML = html; /* all values escaped via esc() at build time */
  }

  function safetyHtml(note) {
    if (!note) return "";
    return '<p class="safety"><strong>Safety:</strong> ' + esc(note) + "</p>";
  }

  function confidenceBadge(value) {
    if (!value) return "";
    var cls = value === "low" ? "badge low" : "badge";
    return ' <span class="' + cls + '">confidence: ' + esc(value) + "</span>";
  }

  function unavailableHtml(note) {
    return "<p><strong>" + esc(note || t("errNoResult")) + "</strong></p>" +
      "<p>Please check a local source. No numbers are guessed.</p>";
  }

  function applyLang(value) {
    document.documentElement.lang = value;
    var buttons = document.querySelectorAll(".lang button");
    buttons.forEach(function (btn) {
      btn.setAttribute("aria-pressed", btn.dataset.lang === value ? "true" : "false");
    });
    document.querySelectorAll("[data-i18n]").forEach(function (el) {
      el.textContent = t(el.dataset.i18n);
    });
    var loading = document.querySelector("[data-loading]");
    if (loading && !loading.hidden) loading.textContent = t("loading");
  }

  function checkFile(file, allowedExts) {
    if (!file || !file.name) return t("errRequired");
    var name = file.name.toLowerCase();
    var ok = allowedExts.some(function (ext) { return name.endsWith(ext); });
    if (!ok) return t("errFileType") + allowedExts.join(", ");
    if (file.size > 10 * 1024 * 1024) return t("errFileSize");
    if (file.size === 0) return t("errRequired");
    return "";
  }

  /* ---- page wiring ---- */

  function wireRegister(form) {
    var parts = ui(form.parentElement);
    form.addEventListener("submit", async function (ev) {
      ev.preventDefault();
      showError(parts.error, "");
      var data = new FormData(form);
      var payload = {
        name: (data.get("name") || "").toString().trim(),
        phone: (data.get("phone") || "").toString().trim(),
        preferred_language: lang(),
      };
      ["village", "district"].forEach(function (key) {
        var v = (data.get(key) || "").toString().trim();
        if (v) payload[key] = v;
      });
      if (!payload.name || !payload.phone) {
        showError(parts.error, t("errRequired"));
        return;
      }
      showLoading(parts.loading, true);
      try {
        var created = await api("/farmers/", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload),
        });
        showResult(parts.result,
          "<p><strong>Farmer ID: " + esc(created.id) + "</strong></p>" +
          "<p>Name: " + esc(created.name) + " | Phone: " + esc(created.phone) + "</p>" +
          "<p>Save this ID. Use it for chat and rescue plan.</p>");
      } catch (err) {
        showError(parts.error, err.message || t("errNetwork"));
      } finally {
        showLoading(parts.loading, false);
      }
    });
  }

  function wireDashboard() {
    var parts = ui(document);
    var tiles = document.getElementById("status-tiles");
    if (!tiles) return;
    var checks = [
      ["AI", "/ai/status"], ["Chat", "/chat/status"],
      ["Voice", "/voice/status"], ["Image", "/image/status"],
      ["Weather", "/weather/status"], ["Mandi", "/mandi/status"],
      ["Plan", "/plan/status"], ["WhatsApp", "/whatsapp/status"],
    ];
    showLoading(parts.loading, true);
    Promise.all(checks.map(function (item) {
      return api(item[1]).then(
        function (body) {
          return { name: item[0], ok: true, text: body.status || body.mode || "ready" };
        },
        function (err) {
          return { name: item[0], ok: false, text: err.message || t("errNetwork") };
        }
      );
    })).then(function (rows) {
      tiles.innerHTML = rows.map(function (row) {
        var dot = row.ok ? "dot ok" : "dot bad";
        return "<li><span class=\"" + dot + "\"></span><strong>" +
          esc(row.name) + ":</strong> " + esc(row.text) + "</li>";
      }).join("");
      showLoading(parts.loading, false);
    });
  }

  function wireChat(form) {
    var parts = ui(form.parentElement);
    var log = document.createElement("div");
    parts.result.appendChild(log);
    form.addEventListener("submit", async function (ev) {
      ev.preventDefault();
      showError(parts.error, "");
      var data = new FormData(form);
      var farmerId = parseInt((data.get("farmer_id") || "").toString().trim(), 10);
      var message = (data.get("message") || "").toString().trim();
      if (!farmerId || farmerId <= 0) { showError(parts.error, t("errBadId")); return; }
      if (!message) { showError(parts.error, t("errRequired")); return; }
      parts.result.hidden = false;
      log.insertAdjacentHTML("beforeend",
        '<div class="msg farmer">' + esc(message) + "</div>");
      form.message.value = "";
      showLoading(parts.loading, true);
      try {
        var ans = await api("/chat", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ farmer_id: farmerId, message: message, language: lang() }),
        });
        var html = '<div class="msg assistant">' + esc(ans.reply);
        if (ans.follow_up_questions && ans.follow_up_questions.length) {
          html += "<ul>" + ans.follow_up_questions.map(function (q) {
            return "<li>" + esc(q) + "</li>";
          }).join("") + "</ul>";
        }
        html += "</div>" + safetyHtml(ans.safety_note);
        log.insertAdjacentHTML("beforeend", html);
      } catch (err) {
        showError(parts.error, err.message || t("errNetwork"));
      } finally {
        showLoading(parts.loading, false);
      }
    });
  }

  function wireUpload(form, url, allowedExts) {
    var parts = ui(form.parentElement);
    form.addEventListener("submit", async function (ev) {
      ev.preventDefault();
      showError(parts.error, "");
      var input = form.querySelector('input[type="file"]');
      var file = input && input.files ? input.files[0] : null;
      var problem = checkFile(file, allowedExts);
      if (problem) { showError(parts.error, problem); return; }
      var body = new FormData();
      body.append("file", file);
      body.append("language", lang());
      showLoading(parts.loading, true);
      try {
        var ans = await api(url, { method: "POST", body: body });
        var html = "";
        if (ans.transcript !== undefined) {
          html = "<p><strong>Transcript:</strong></p><p>" + esc(ans.transcript) + "</p>";
        } else {
          html = "<p><strong>What we see:</strong> " + esc(ans.observation || "-") + "</p>";
          if (ans.possible_issues && ans.possible_issues.length) {
            html += "<p><strong>Possible issues:</strong></p><ul>" +
              ans.possible_issues.map(function (x) { return "<li>" + esc(x) + "</li>"; }).join("") +
              "</ul>";
          }
          html += "<p>" + confidenceBadge(ans.confidence) + "</p>";
          if (ans.guidance) html += "<p>" + esc(ans.guidance) + "</p>";
          html += safetyHtml(ans.safety_note);
          if (ans.needs_clearer_photo) {
            html += "<p>Tip: send a clearer close-up photo in daylight.</p>";
          }
        }
        showResult(parts.result, html);
      } catch (err) {
        showError(parts.error, err.message || t("errNetwork"));
      } finally {
        showLoading(parts.loading, false);
      }
    });
  }

  function wireWeather(form) {
    var parts = ui(form.parentElement);
    form.addEventListener("submit", async function (ev) {
      ev.preventDefault();
      showError(parts.error, "");
      var data = new FormData(form);
      var city = (data.get("city") || "").toString().trim();
      var lat = (data.get("lat") || "").toString().trim();
      var lon = (data.get("lon") || "").toString().trim();
      var params = new URLSearchParams({ language: lang() });
      if (lat !== "" || lon !== "") {
        if (lat === "" || lon === "") { showError(parts.error, t("errRequired")); return; }
        params.set("lat", lat);
        params.set("lon", lon);
      } else if (city) {
        params.set("city", city);
      } else {
        showError(parts.error, t("errRequired"));
        return;
      }
      showLoading(parts.loading, true);
      try {
        var w = await api("/weather?" + params.toString());
        if (w.status !== "ok") { showResult(parts.result, unavailableHtml(w.note)); return; }
        var html = "<p><strong>" + esc(w.resolved_name || w.location) + "</strong></p>" +
          "<p>Now: " + esc(w.temperature_c) + "°C, rain " + esc(w.precipitation_mm) +
          " mm, wind " + esc(w.wind_kph) + " kph (" + esc(w.condition || "") + ")</p>";
        if (w.daily && w.daily.length) {
          html += "<p><strong>Next days:</strong></p><ul>" + w.daily.slice(0, 4).map(function (d) {
            return "<li>" + esc(d.date) + ": " + esc(d.temp_min_c) + "–" + esc(d.temp_max_c) +
              "°C, rain " + esc(d.rain_mm) + " mm</li>";
          }).join("") + "</ul>";
        }
        if (w.guidance) html += "<p>" + esc(w.guidance) + "</p>";
        showResult(parts.result, html);
      } catch (err) {
        showError(parts.error, err.message || t("errNetwork"));
      } finally {
        showLoading(parts.loading, false);
      }
    });
  }

  function wireMandi(form) {
    var parts = ui(form.parentElement);
    form.addEventListener("submit", async function (ev) {
      ev.preventDefault();
      showError(parts.error, "");
      var data = new FormData(form);
      var crop = (data.get("crop") || "").toString().trim();
      var market = (data.get("market") || "").toString().trim();
      if (!crop) { showError(parts.error, t("errRequired")); return; }
      var params = new URLSearchParams({ crop: crop });
      if (market) params.set("market", market);
      showLoading(parts.loading, true);
      try {
        var m = await api("/mandi?" + params.toString());
        if (m.status !== "ok") { showResult(parts.result, unavailableHtml(m.note)); return; }
        showResult(parts.result,
          "<p><strong>" + esc(m.commodity || crop) + " - " + esc(m.market || market || "-") + "</strong></p>" +
          "<p>Modal price: Rs " + esc(m.modal_price) + " / quintal</p>" +
          "<p>Range: Rs " + esc(m.min_price) + " – Rs " + esc(m.max_price) + "</p>" +
          "<p>Date: " + esc(m.arrival_date || "-") + "</p>");
      } catch (err) {
        showError(parts.error, err.message || t("errNetwork"));
      } finally {
        showLoading(parts.loading, false);
      }
    });
  }

  function wirePlan(form) {
    var parts = ui(form.parentElement);
    form.addEventListener("submit", async function (ev) {
      ev.preventDefault();
      showError(parts.error, "");
      var data = new FormData(form);
      var farmerId = parseInt((data.get("farmer_id") || "").toString().trim(), 10);
      if (!farmerId || farmerId <= 0) { showError(parts.error, t("errBadId")); return; }
      showLoading(parts.loading, true);
      try {
        var p = await api("/plan/" + farmerId + "?language=" + lang());
        var html = "<h2>" + esc(p.title) + confidenceBadge(p.confidence) + "</h2>" +
          "<p>" + esc(p.summary) + "</p>";
        if (p.immediate_steps && p.immediate_steps.length) {
          html += "<p><strong>Safe steps:</strong></p><ol>" +
            p.immediate_steps.map(function (s) { return "<li>" + esc(s) + "</li>"; }).join("") + "</ol>";
        }
        if (p.questions_for_expert && p.questions_for_expert.length) {
          html += "<p><strong>Ask the expert:</strong></p><ul>" +
            p.questions_for_expert.map(function (q) { return "<li>" + esc(q) + "</li>"; }).join("") + "</ul>";
        }
        html += safetyHtml(p.safety_note);
        html += '<p><a href="/plan/' + farmerId + '/card?language=' + lang() +
          '" target="_blank" rel="noopener">Open shareable card</a></p>';
        showResult(parts.result, html);
      } catch (err) {
        showError(parts.error, err.message || t("errNetwork"));
      } finally {
        showLoading(parts.loading, false);
      }
    });
  }

  document.addEventListener("DOMContentLoaded", function () {
    document.querySelectorAll(".lang button").forEach(function (btn) {
      btn.addEventListener("click", function () { setLang(btn.dataset.lang); });
    });
    applyLang(lang());
    var get = function (id) { return document.getElementById(id); };
    if (get("register-form")) wireRegister(get("register-form"));
    if (get("status-tiles")) wireDashboard();
    if (get("chat-form")) wireChat(get("chat-form"));
    if (get("image-form")) wireUpload(get("image-form"), "/image/analyse", [".jpg", ".jpeg", ".png", ".webp"]);
    if (get("voice-form")) wireUpload(get("voice-form"), "/voice/transcribe", [".mp3", ".wav", ".m4a", ".ogg", ".webm"]);
    if (get("weather-form")) wireWeather(get("weather-form"));
    if (get("mandi-form")) wireMandi(get("mandi-form"));
    if (get("plan-form")) wirePlan(get("plan-form"));
  });
})();
