/*!
 * University of Layyah chat widget — one file, no dependencies.
 * Add to any page:
 *   <script src="https://YOUR-SERVER/static/chatbot.js" defer></script>
 * Optional attributes: data-api="https://YOUR-SERVER"  data-color="#0f4c5c"
 */
(function () {
  "use strict";
  if (window.__ulChatbot) return;
  window.__ulChatbot = true;

  var script = document.currentScript;
  var apiBase = (script && script.dataset.api) || (script && script.src ? new URL(script.src).origin : "");
  var color = (script && script.dataset.color) || "#0f4c5c";
  var logoUrl = (script && script.dataset.logo) || (apiBase ? apiBase + "/static/logo.png" : "/static/logo.png");
  var STORE_KEY = "ul-chatbot-v1";

  var GREETING =
    "Assalam o Alaikum! Main University of Layyah ka AI assistant hoon. " +
    "Admissions, fee, programs ya contact ke baare mein Urdu, Roman Urdu ya English mein poochein.";

  var CSS = [
    "@import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700&family=Outfit:wght@500;600;700&display=swap');",
    ":host{all:initial}",
    "*{box-sizing:border-box}",
    ".w{--c:" + color + ";--c-dark:#064e3b;--c-light:#059669;--gold:#d97706;--gold-light:#fbbf24;--ink:#0f172a;" +
      "--ink-light:#334155;--mut:#64748b;--line:#e2e8f0;--bot:#ffffff;--bot-border:#e2e8f0;--bg-subtle:#f8fafc;" +
      "font-family:'Plus Jakarta Sans',system-ui,-apple-system,'Segoe UI',Roboto,'Noto Nastaliq Urdu',sans-serif;" +
      "color:var(--ink);font-size:14.5px;line-height:1.55;-webkit-font-smoothing:antialiased}",
    
    /* Floating Launch Button */
    ".launch-wrap{position:fixed;right:24px;bottom:24px;z-index:2147483000;display:flex;flex-direction:column;align-items:flex-end;gap:10px}",
    ".launch-callout{background:#ffffff;color:var(--ink);padding:10px 14px;border-radius:14px;box-shadow:0 12px 30px rgba(6,78,59,.18),0 2px 8px rgba(0,0,0,.06);" +
      "border:1px solid rgba(226,232,240,.9);font-size:12.5px;max-width:260px;display:flex;align-items:center;gap:9px;animation:fade-up .4s cubic-bezier(.16,1,.3,1);" +
      "cursor:pointer;position:relative;transition:transform .2s ease}",
    ".launch-callout:hover{transform:translateY(-2px)}",
    ".launch-callout-close{border:0;background:none;color:var(--mut);cursor:pointer;padding:2px 4px;font-size:14px;border-radius:4px}",
    ".launch-callout-close:hover{color:var(--ink);background:#f1f5f9}",
    ".launch{display:inline-flex;align-items:center;gap:10px;background:linear-gradient(135deg,#064e3b 0%,#065f46 50%,#047857 100%);" +
      "color:#fff;border:1.5px solid rgba(251,191,36,.4);border-radius:999px;padding:8px 18px 8px 8px;cursor:pointer;" +
      "font-family:'Outfit','Plus Jakarta Sans',sans-serif;font-weight:600;font-size:14px;letter-spacing:.2px;" +
      "box-shadow:0 8px 25px rgba(6,78,59,.35),0 2px 6px rgba(0,0,0,.1);transition:all .25s cubic-bezier(.16,1,.3,1)}",
    ".launch:hover{transform:translateY(-3px) scale(1.02);box-shadow:0 14px 32px rgba(6,78,59,.42);border-color:#fbbf24}",
    ".launch:active{transform:translateY(0) scale(.98)}",
    ".launch-logo-box{position:relative;width:34px;height:34px;border-radius:50%;background:#ffffff;padding:2px;display:grid;place-items:center;flex-shrink:0;box-shadow:0 0 0 2px rgba(251,191,36,.6)}",
    ".launch-logo{width:100%;height:100%;border-radius:50%;object-fit:contain}",
    ".radar-pulse{position:absolute;right:-1px;bottom:-1px;width:10px;height:10px;background:#10b981;border-radius:50%;border:2px solid #fff}",
    ".radar-pulse::after{content:'';position:absolute;inset:-4px;border-radius:50%;border:2px solid #10b981;animation:radar-ring 1.8s infinite cubic-bezier(0,0,.2,1)}",
    "@keyframes radar-ring{0%{transform:scale(.5);opacity:1}100%{transform:scale(2.2);opacity:0}}",
    "@keyframes fade-up{from{opacity:0;transform:translateY(8px)}to{opacity:1;transform:translateY(0)}}",

    /* Panel Card */
    ".panel{position:fixed;right:24px;bottom:24px;z-index:2147483001;width:400px;max-width:calc(100vw - 28px);" +
      "height:min(660px,calc(100vh - 44px));background:#ffffff;border-radius:20px;display:flex;flex-direction:column;" +
      "overflow:hidden;box-shadow:0 24px 60px -12px rgba(6,78,59,.3),0 8px 24px -4px rgba(0,0,0,.08);" +
      "border:1px solid rgba(226,232,240,.9);transform-origin:bottom right;transition:all .25s cubic-bezier(.16,1,.3,1)}",
    ".panel[hidden],.launch-wrap[hidden]{display:none}",
    ".panel.open{animation:pop-in .26s cubic-bezier(.16,1,.3,1)}",
    "@keyframes pop-in{from{opacity:0;transform:scale(.94) translateY(14px)}to{opacity:1;transform:none}}",

    /* Executive Header */
    ".hd{background:linear-gradient(135deg,#064e3b 0%,#065f46 60%,#047857 100%);color:#fff;padding:14px 16px;display:flex;align-items:center;gap:12px;" +
      "border-bottom:3px solid var(--gold);box-shadow:0 4px 12px rgba(0,0,0,.08);position:relative}",
    ".hd-logo-wrap{position:relative;width:40px;height:40px;border-radius:50%;background:#ffffff;padding:2px;display:grid;place-items:center;flex-shrink:0;box-shadow:0 0 0 2px var(--gold-light),0 4px 10px rgba(0,0,0,.15)}",
    ".hd-logo-wrap img{width:100%;height:100%;object-fit:contain;border-radius:50%}",
    ".hd .t{flex:1;min-width:0}",
    ".hd-title-row{display:flex;align-items:center;gap:6px}",
    ".hd b{font-family:'Outfit','Plus Jakarta Sans',sans-serif;font-size:16px;font-weight:700;letter-spacing:.2px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}",
    ".verified-badge{display:inline-flex;color:#fbbf24;width:14px;height:14px;flex-shrink:0}",
    ".hd-sub-row{display:flex;align-items:center;gap:7px;margin-top:2px}",
    ".hd span{font-size:11.5px;opacity:.9;font-weight:500;color:#e2e8f0}",
    ".status-pill{display:inline-flex;align-items:center;gap:4px;padding:1px 6px;border-radius:10px;background:rgba(16,185,129,.2);border:1px solid rgba(16,185,129,.4);font-size:10.5px;font-weight:600;color:#6ee7b7}",
    ".status-dot{width:6px;height:6px;border-radius:50%;background:#10b981;animation:beacon 2s infinite ease-in-out}",
    "@keyframes beacon{0%,100%{opacity:.6;transform:scale(.9)}50%{opacity:1;transform:scale(1.2)}}",
    ".hd-actions{display:flex;align-items:center;gap:4px}",
    ".ib{background:rgba(255,255,255,.1);border:0;color:#fff;width:32px;height:32px;border-radius:8px;cursor:pointer;display:grid;place-items:center;transition:all .18s ease}",
    ".ib:hover{background:rgba(255,255,255,.22);transform:scale(1.05)}",
    ".ib:active{transform:scale(.95)}",
    ".ib svg{width:16px;height:16px}",

    /* Chat Log Feed */
    ".log{flex:1;overflow-y:auto;padding:16px;display:flex;flex-direction:column;gap:12px;background:#f8fafc;scroll-behavior:smooth}",
    ".msg-row{display:flex;gap:8px;align-items:flex-end}",
    ".msg-row.me{justify-content:flex-end}",
    ".bot-avatar{width:26px;height:26px;border-radius:50%;background:#fff;border:1px solid #cbd5e1;padding:2px;display:grid;place-items:center;flex-shrink:0;box-shadow:0 1px 3px rgba(0,0,0,.08)}",
    ".bot-avatar img{width:100%;height:100%;object-fit:contain;border-radius:50%}",
    ".m{max-width:86%;padding:11px 15px;border-radius:16px;word-wrap:break-word;overflow-wrap:anywhere;position:relative;box-shadow:0 2px 6px rgba(0,0,0,.03)}",
    ".m.bot{background:#ffffff;border:1px solid #e2e8f0;border-left:3.5px solid #059669;border-bottom-left-radius:4px;color:var(--ink)}",
    ".m.me{background:linear-gradient(135deg,#064e3b 0%,#047857 100%);color:#fff;border-bottom-right-radius:4px;box-shadow:0 4px 12px rgba(6,78,59,.2)}",
    ".m p{margin:0}.m p+p,.m p+ul,.m ul+p{margin-top:7px}",
    ".m ul{margin:0;padding-inline-start:18px}",
    ".m li{margin-bottom:3px}",
    ".m a{color:#047857;text-decoration:underline;font-weight:600}",
    ".m.me a{color:#fbbf24;text-decoration:underline}",
    ".m.err{background:#fef2f2;border-left:3.5px solid #ef4444;border-color:#fecaca;color:#991b1b}",

    /* Interactive Copy Button */
    ".msg-meta{display:flex;align-items:center;justify-content:flex-end;gap:8px;margin-top:6px;padding-top:4px;border-top:1px solid #f1f5f9}",
    ".copy-btn{border:0;background:none;color:var(--mut);cursor:pointer;padding:2px 6px;border-radius:4px;font-size:11px;display:inline-flex;align-items:center;gap:4px;transition:all .15s ease}",
    ".copy-btn:hover{color:var(--c-light);background:#f1f5f9}",
    ".copy-btn svg{width:12px;height:12px}",

    /* Streaming Cursor */
    ".typing-cursor{display:inline-block;width:2px;height:14px;background:#059669;margin-left:3px;vertical-align:middle;animation:cursor-blink .8s infinite}",
    "@keyframes cursor-blink{0%,100%{opacity:1}50%{opacity:0}}",

    /* Official Sources Citation */
    ".src-box{margin-top:10px;padding-top:8px;border-top:1px dashed #cbd5e1}",
    ".src-label{font-size:11px;font-weight:700;color:var(--mut);text-transform:uppercase;letter-spacing:.4px;margin-bottom:5px;display:flex;align-items:center;gap:4px}",
    ".src{display:flex;flex-wrap:wrap;gap:6px}",
    ".src-item{display:inline-flex;align-items:center;gap:5px;font-size:11.5px;font-weight:600;text-decoration:none;color:#065f46;background:#f0fdf4;border:1px solid #bbf7d0;padding:3px 9px;border-radius:999px;transition:all .18s ease;max-width:100%;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}",
    ".src-item:hover{background:#dcfce7;border-color:#86efac;transform:translateY(-1px);box-shadow:0 2px 6px rgba(6,78,59,.1)}",
    ".src-item svg{width:12px;height:12px;flex-shrink:0;color:#059669}",

    /* Action Buttons */
    ".act-box{display:flex;flex-wrap:wrap;gap:6px;margin-top:10px;padding-top:10px;border-top:1px dashed #cbd5e1}",
    ".act-btn{display:inline-flex;align-items:center;gap:6px;background:#ffffff;color:#065f46;border:1.5px solid #059669;" +
      "padding:5px 12px;border-radius:999px;font-size:12px;font-weight:600;text-decoration:none;cursor:pointer;" +
      "transition:all .18s cubic-bezier(.16,1,.3,1);box-shadow:0 2px 6px rgba(6,78,59,.08)}",
    ".act-btn:hover{background:linear-gradient(135deg,#064e3b 0%,#047857 100%);color:#fff;border-color:transparent;transform:translateY(-1.5px);box-shadow:0 4px 12px rgba(6,78,59,.25)}",
    ".act-btn.wa{color:#15803d;border-color:#22c55e;background:#f0fdf4}",
    ".act-btn.wa:hover{background:#16a34a;color:#fff}",
    ".act-btn svg{width:13px;height:13px;flex-shrink:0}",

    /* Suggestion Chips */
    ".chips{display:flex;overflow-x:auto;gap:6px;padding:8px 16px 10px;background:#f8fafc;border-top:1px solid #edf2f7;scrollbar-width:none}",
    ".chips::-webkit-scrollbar{display:none}",
    ".chip{background:#ffffff;border:1px solid #cbd5e1;color:#0f172a;border-radius:999px;padding:5px 11px;" +
      "font-size:12px;font-weight:600;cursor:pointer;white-space:nowrap;display:inline-flex;align-items:center;gap:5px;transition:all .18s ease;box-shadow:0 1px 3px rgba(0,0,0,.04)}",
    ".chip:hover{border-color:#059669;color:#065f46;background:#f0fdf4;transform:translateY(-1px);box-shadow:0 3px 8px rgba(6,78,59,.1)}",
    ".chip:active{transform:scale(.96)}",

    /* Loading Dots */
    ".dots{display:inline-flex;gap:5px;padding:4px 2px;align-items:center}",
    ".dots i{width:7px;height:7px;border-radius:50%;background:#059669;animation:bounce-pulse 1.1s infinite ease-in-out}",
    ".dots i:nth-child(2){animation-delay:.18s}.dots i:nth-child(3){animation-delay:.36s}",
    "@keyframes bounce-pulse{0%,80%,100%{opacity:.25;transform:scale(.8)}40%{opacity:1;transform:scale(1.2)}}",

    /* Input Footer & Audio Visualizer */
    "form{display:flex;gap:8px;padding:10px 14px;border-top:1px solid #e2e8f0;background:#ffffff;align-items:flex-end}",
    "textarea{flex:1;resize:none;border:1.5px solid #cbd5e1;border-radius:14px;padding:9px 12px;font:inherit;font-size:14px;" +
      "max-height:110px;min-height:42px;color:var(--ink);background:#ffffff;transition:border-color .2s,box-shadow .2s;line-height:1.4}",
    "textarea:focus{outline:0;border-color:#059669;box-shadow:0 0 0 3px rgba(5,150,105,.14)}",
    ".mic{background:#f8fafc;color:#065f46;border:1.5px solid #cbd5e1;border-radius:14px;width:42px;height:42px;cursor:pointer;" +
      "display:grid;place-items:center;flex-shrink:0;transition:all .2s ease;position:relative}",
    ".mic:hover{background:#f0fdf4;border-color:#059669;color:#047857}",
    ".mic.listening{background:#fee2e2;color:#dc2626;border-color:#ef4444;animation:mic-alert 1.2s infinite ease-in-out}",
    ".mic[hidden]{display:none}",
    ".mic svg{width:18px;height:18px}",
    "@keyframes mic-alert{0%,100%{transform:scale(1);box-shadow:0 0 0 0 rgba(220,38,38,.4)}50%{transform:scale(1.05);box-shadow:0 0 0 6px rgba(220,38,38,0)}}",
    ".soundwave{display:none;position:absolute;inset:0;border-radius:14px;align-items:center;justify-content:center;gap:2.5px;background:#ef4444}",
    ".mic.listening .soundwave{display:flex}",
    ".mic.listening svg{display:none}",
    ".soundwave-bar{width:2.5px;height:14px;background:#ffffff;border-radius:2px;animation:soundwave-bounce .6s infinite alternate ease-in-out}",
    ".soundwave-bar:nth-child(2){animation-delay:.15s;height:20px}",
    ".soundwave-bar:nth-child(3){animation-delay:.3s;height:16px}",
    ".soundwave-bar:nth-child(4){animation-delay:.45s;height:10px}",
    "@keyframes soundwave-bounce{0%{transform:scaleY(.3)}100%{transform:scaleY(1)}}",
    ".send{background:linear-gradient(135deg,#064e3b 0%,#047857 100%);color:#fff;border:0;border-radius:14px;width:44px;height:42px;cursor:pointer;" +
      "display:grid;place-items:center;flex-shrink:0;transition:all .2s ease;box-shadow:0 4px 10px rgba(6,78,59,.2)}",
    ".send:hover{transform:scale(1.04);box-shadow:0 6px 14px rgba(6,78,59,.3)}",
    ".send:active{transform:scale(.96)}",
    ".send:disabled,.mic:disabled{opacity:.45;cursor:default;transform:none;box-shadow:none}",
    ".send svg{width:18px;height:18px}",
    ".note{font-size:11px;color:var(--mut);text-align:center;padding:0 12px 8px;background:#ffffff;display:flex;align-items:center;justify-content:center;gap:4px}",
    "button:focus-visible,a:focus-visible,textarea:focus-visible{outline:2px solid var(--gold);outline-offset:2px}",
    
    /* Responsive Breakpoints */
    "@media (max-width:520px){.panel{right:0;bottom:0;width:100vw;max-width:none;height:100%;border-radius:0;border:0}" +
      ".launch-wrap{right:16px;bottom:16px}}",
    "@media (prefers-reduced-motion:reduce){.panel.open,.launch-callout{animation:none}.log{scroll-behavior:auto}.dots i,.soundwave-bar,.radar-pulse::after{animation:none}}"
  ].join("\n");

  var ICON_CHAT = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 12a8 8 0 0 1-11.6 7.1L4 20l1-4.3A8 8 0 1 1 21 12z"/></svg>';
  var ICON_CLOSE = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round"><path d="M6 6l12 12M18 6L6 18"/></svg>';
  var ICON_RESET = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 12a9 9 0 1 0 3-6.7L3 8"/><path d="M3 3v5h5"/></svg>';
  var ICON_SEND = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M22 2L11 13"/><path d="M22 2l-7 20-4-9-9-4 20-7z"/></svg>';
  var ICON_MIC = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 1a3 3 0 0 0-3 3v8a3 3 0 0 0 6 0V4a3 3 0 0 0-3-3z"/><path d="M19 10v2a7 7 0 0 1-14 0v-2"/><line x1="12" y1="19" x2="12" y2="23"/><line x1="8" y1="23" x2="16" y2="23"/></svg>';
  var ICON_VERIFIED = '<svg class="verified-badge" viewBox="0 0 24 24" fill="currentColor"><path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm-2 15l-5-5 1.41-1.41L10 14.17l7.59-7.59L19 8l-9 9z"/></svg>';
  var ICON_COPY = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="9" y="9" width="13" height="13" rx="2" ry="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg>';
  var ICON_DOC = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/></svg>';
  var ICON_GLOBE = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><line x1="2" y1="12" x2="22" y2="12"/><path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z"/></svg>';
  var ICON_SHIELD = '<svg style="width:12px;height:12px;display:inline-block;vertical-align:middle;color:#059669" viewBox="0 0 24 24" fill="currentColor"><path d="M12 1L3 5v6c0 5.55 3.84 10.74 9 12 5.16-1.26 9-6.45 9-12V5l-9-4zm-2 16l-4-4 1.41-1.41L10 14.17l6.59-6.59L18 9l-8 8z"/></svg>';

  var host = document.createElement("div");
  host.setAttribute("data-ul-chatbot", "");
  var root = host.attachShadow({ mode: "open" });
  root.innerHTML =
    "<style>" + CSS + "</style>" +
    '<div class="w">' +
      '<div class="launch-wrap">' +
        '<div class="launch-callout" role="button" aria-label="Sawal poochein" title="Sawal poochein">' +
          '<span>👋 <strong>Assalam-o-Alaikum!</strong> University AI Desk se sawal poochein</span>' +
          '<button class="launch-callout-close" aria-label="Band karein">&times;</button>' +
        '</div>' +
        '<button class="launch" aria-label="Chat kholein">' +
          '<div class="launch-logo-box">' +
            '<img class="launch-logo" src="' + logoUrl + '" alt="UL" onerror="this.style.display=\'none\'" />' +
            '<span class="radar-pulse"></span>' +
          '</div>' +
          '<span>UL Assistant • پوچھیں</span>' +
        '</button>' +
      '</div>' +
      '<section class="panel" role="dialog" aria-label="UL Assistant" hidden>' +
        '<div class="hd">' +
          '<div class="hd-logo-wrap">' +
            '<img src="' + logoUrl + '" alt="UL Logo" onerror="this.parentNode.style.display=\'none\'" />' +
          '</div>' +
          '<div class="t">' +
            '<div class="hd-title-row">' +
              '<b>University of Layyah</b>' +
              ICON_VERIFIED +
            '</div>' +
            '<div class="hd-sub-row">' +
              '<span>AI Admissions & Student Desk</span>' +
              '<span class="status-pill"><span class="status-dot"></span>Live</span>' +
            '</div>' +
          '</div>' +
          '<div class="hd-actions">' +
            '<button class="ib reset" aria-label="Nayi baat-cheet" title="Nayi baat-cheet">' + ICON_RESET + "</button>" +
            '<button class="ib close" aria-label="Chat band karein" title="Band karein">' + ICON_CLOSE + "</button>" +
          '</div>' +
        '</div>' +
        '<div class="log" role="log" aria-live="polite"></div>' +
        '<div class="chips"></div>' +
        '<form>' +
          '<textarea rows="1" maxlength="600" placeholder="Admissions, fee, programs ya merit list ke baare mein likhein..." aria-label="Apna sawal"></textarea>' +
          '<button class="mic" type="button" aria-label="Bol kar sawal poochein" title="Bol kar sawal poochein">' +
            ICON_MIC +
            '<div class="soundwave">' +
              '<span class="soundwave-bar"></span><span class="soundwave-bar"></span>' +
              '<span class="soundwave-bar"></span><span class="soundwave-bar"></span>' +
            '</div>' +
          '</button>' +
          '<button class="send" type="submit" aria-label="Bhejein">' + ICON_SEND + "</button>" +
        '</form>' +
        '<div class="note">' + ICON_SHIELD + ' Official AI Desk • Verified against ul.edu.pk records</div>' +
      "</section>" +
    "</div>";

  var $ = function (s) { return root.querySelector(s); };
  var launchWrap = $(".launch-wrap"), launch = $(".launch"), callout = $(".launch-callout"),
      calloutClose = $(".launch-callout-close"), panel = $(".panel"), log = $(".log"),
      chips = $(".chips"), form = $("form"), input = $("textarea"), sendBtn = $(".send"), micBtn = $(".mic");

  // ---- safe text rendering (escape first, then allow bold / links / bullets) ----
  function esc(s) {
    return s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
  }
  function inline(s) {
    s = esc(s).replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>");
    return s.replace(/(https?:\/\/[^\s<]+)/g, function (u) {
      var tail = (u.match(/[.,;:!?)]+$/) || [""])[0];
      var clean = tail ? u.slice(0, -tail.length) : u;
      return '<a href="' + clean + '" target="_blank" rel="noopener noreferrer">' + clean + "</a>" + tail;
    });
  }
  function render(text) {
    var out = [], list = [];
    function flush() { if (list.length) { out.push("<ul>" + list.join("") + "</ul>"); list = []; } }
    text.split("\n").forEach(function (line) {
      var m = line.match(/^\s*(?:[-*•])\s+(.*)$/);
      if (m) { list.push("<li>" + inline(m[1]) + "</li>"); return; }
      flush();
      if (line.trim()) out.push("<p>" + inline(line) + "</p>");
    });
    flush();
    return out.join("");
  }

  var ACT_ICONS = {
    phone: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M22 16.92v3a2 2 0 0 1-2.18 2 19.79 19.79 0 0 1-8.63-3.07 19.5 19.5 0 0 1-6-6 19.79 19.79 0 0 1-3.07-8.67A2 2 0 0 1 4.11 2h3a2 2 0 0 1 2 1.72 12.84 12.84 0 0 0 .7 2.81 2 2 0 0 1-.45 2.11L8.09 9.91a16 16 0 0 0 6 6l1.27-1.27a2 2 0 0 1 2.11-.45 12.84 12.84 0 0 0 2.81.7A2 2 0 0 1 22 16.92z"/></svg>',
    whatsapp: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 11.5a8.38 8.38 0 0 1-.9 3.8 8.5 8.5 0 0 1-7.6 4.7 8.38 8.38 0 0 1-3.8-.9L3 21l1.9-5.7a8.38 8.38 0 0 1-.9-3.8 8.5 8.5 0 0 1 4.7-7.6 8.38 8.38 0 0 1 3.8-.9h.5a8.48 8.48 0 0 1 8 8v.5z"/></svg>',
    document: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/></svg>',
    list: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><line x1="8" y1="6" x2="21" y2="6"/><line x1="8" y1="12" x2="21" y2="12"/><line x1="8" y1="18" x2="21" y2="18"/><line x1="3" y1="6" x2="3.01" y2="6"/><line x1="3" y1="12" x2="3.01" y2="12"/><line x1="3" y1="18" x2="3.01" y2="18"/></svg>',
    home: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 9l9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/><polyline points="9 22 9 12 15 12 15 22"/></svg>',
    award: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="8" r="7"/><polyline points="8.21 13.89 7 23 12 20 17 23 15.79 13.88"/></svg>',
    bus: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="3" width="18" height="15" rx="3"/><line x1="3" y1="10" x2="21" y2="10"/><circle cx="7" cy="15" r="1"/><circle cx="17" cy="15" r="1"/><path d="M5 18v2a1 1 0 0 0 1 1h1a1 1 0 0 0 1-1v-2"/><path d="M16 18v2a1 1 0 0 0 1 1h1a1 1 0 0 0 1-1v-2"/></svg>',
    portal: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/><polyline points="15 3 21 3 21 9"/><line x1="10" y1="14" x2="21" y2="3"/></svg>'
  };

  var QUICK = [
    { text: "Admission kaise karein?", icon: "🎓" },
    { text: "Fee structure kya hai?", icon: "💳" },
    { text: "Eligibility criteria kya hai?", icon: "📋" },
    { text: "Kon kon se programs hain?", icon: "🏛️" },
    { text: "Contact details do", icon: "📞" }
  ];

  var history = [];
  try { history = JSON.parse(sessionStorage.getItem(STORE_KEY) || "[]"); } catch (e) { history = []; }
  var busy = false;

  function updateMessage(el, text, sources, actions) {
    el.innerHTML = render(text);
    if (sources && sources.length) {
      var box = document.createElement("div");
      box.className = "src-box";
      var label = document.createElement("div");
      label.className = "src-label";
      label.innerHTML = ICON_SHIELD + '<span>Official Verified Sources:</span>';
      box.appendChild(label);

      var srcList = document.createElement("div");
      srcList.className = "src";
      sources.forEach(function (s) {
        var a = document.createElement("a");
        a.className = "src-item";
        a.href = s.url; a.target = "_blank"; a.rel = "noopener noreferrer";
        var isPdf = (s.url || "").toLowerCase().indexOf(".pdf") !== -1 || (s.title || "").toLowerCase().indexOf("pdf") !== -1;
        a.innerHTML = (isPdf ? ICON_DOC : ICON_GLOBE) + "<span>" + esc(s.title) + "</span>";
        a.title = s.title;
        srcList.appendChild(a);
      });
      box.appendChild(srcList);
      el.appendChild(box);
    }
    if (actions && actions.length) {
      var actBox = document.createElement("div");
      actBox.className = "act-box";
      actions.forEach(function (act) {
        var a = document.createElement("a");
        var isWa = act.icon === "whatsapp";
        a.className = "act-btn" + (isWa ? " wa" : "");
        a.href = act.url;
        if (!act.url.startsWith("tel:") && !act.url.startsWith("mailto:") && !act.url.startsWith("javascript:")) {
          a.target = "_blank";
          a.rel = "noopener noreferrer";
        }
        var iconSvg = ACT_ICONS[act.icon] || ACT_ICONS.portal;
        a.innerHTML = iconSvg + "<span>" + esc(act.label) + "</span>";
        actBox.appendChild(a);
      });
      el.appendChild(actBox);
    }

    // Add copy button to non-error assistant answers
    if (el.classList.contains("bot") && !el.classList.contains("err") && text.trim()) {
      var meta = document.createElement("div");
      meta.className = "msg-meta";
      var copyBtn = document.createElement("button");
      copyBtn.type = "button";
      copyBtn.className = "copy-btn";
      copyBtn.innerHTML = ICON_COPY + "<span>Copy</span>";
      copyBtn.title = "Jawab copy karein";
      copyBtn.addEventListener("click", function () {
        if (navigator.clipboard) {
          navigator.clipboard.writeText(text).then(function () {
            copyBtn.innerHTML = "✓ <span>Copied!</span>";
            copyBtn.style.color = "#059669";
            setTimeout(function () {
              copyBtn.innerHTML = ICON_COPY + "<span>Copy</span>";
              copyBtn.style.color = "";
            }, 1800);
          });
        }
      });
      meta.appendChild(copyBtn);
      el.appendChild(meta);
    }
  }

  function addMessage(role, text, sources, isError, actions) {
    var row = document.createElement("div");
    row.className = "msg-row " + (role === "user" ? "me" : "bot");

    if (role !== "user") {
      var avatar = document.createElement("div");
      avatar.className = "bot-avatar";
      avatar.innerHTML = '<img src="' + logoUrl + '" alt="UL" onerror="this.parentNode.style.display=\'none\'" />';
      row.appendChild(avatar);
    }

    var el = document.createElement("div");
    el.className = "m " + (role === "user" ? "me" : "bot") + (isError ? " err" : "");
    el.setAttribute("dir", "auto");
    updateMessage(el, text, sources, actions);
    row.appendChild(el);
    log.appendChild(row);
    log.scrollTop = log.scrollHeight;
    return el;
  }

  function save() {
    try { sessionStorage.setItem(STORE_KEY, JSON.stringify(history.slice(-20))); } catch (e) {}
  }

  function showChips(on) {
    chips.innerHTML = "";
    if (!on) return;
    QUICK.forEach(function (q) {
      var b = document.createElement("button");
      b.type = "button"; b.className = "chip";
      b.innerHTML = "<span>" + q.icon + "</span><span>" + esc(q.text) + "</span>";
      b.addEventListener("click", function () { send(q.text); });
      chips.appendChild(b);
    });
  }

  function start() {
    log.innerHTML = "";
    addMessage("assistant", GREETING);
    history.forEach(function (t) { addMessage(t.role, t.content); });
    showChips(history.length === 0);
  }

  function setBusy(v) {
    busy = v;
    sendBtn.disabled = v;
    input.disabled = v;
    if (micBtn) micBtn.disabled = v;
  }

  function send(text) {
    text = (text || "").trim();
    if (!text || busy) return;
    showChips(false);
    addMessage("user", text);
    var past = history.slice(-8).map(function (t) {
      return {
        role: t.role === "assistant" ? "assistant" : "user",
        content: (t.content || "").slice(0, 1500)
      };
    });
    history.push({ role: "user", content: text });
    input.value = ""; input.style.height = "auto";
    setBusy(true);

    var typing = document.createElement("div");
    typing.className = "m bot";
    typing.innerHTML = '<span class="dots" aria-label="Jawab likh raha hai"><i></i><i></i><i></i></span>';
    log.appendChild(typing); log.scrollTop = log.scrollHeight;

    var botEl = null;
    var fullAnswer = "";
    var streamAborted = false;

    // Timeout watchdog (22 seconds)
    var controller = typeof AbortController !== "undefined" ? new AbortController() : null;
    var timer = setTimeout(function () {
      if (controller) {
        streamAborted = true;
        controller.abort();
      }
    }, 22000);

    fetch(apiBase + "/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      signal: controller ? controller.signal : undefined,
      body: JSON.stringify({ message: text, history: past, stream: true })
    })
      .then(function (res) {
        clearTimeout(timer);
        if (!res.ok) {
          return res.json().catch(function () { return {}; }).then(function (d) {
            throw new Error(d.detail || "Server error (" + res.status + ")");
          });
        }
        var ctype = res.headers.get("content-type") || "";
        var isStream = ctype.indexOf("text/event-stream") !== -1 && Boolean(res.body);
        if (!isStream) {
          return res.json().then(function (d) {
            if (typing.parentNode) typing.remove();
            addMessage("assistant", d.answer, d.sources, false, d.actions);
            history.push({ role: "assistant", content: d.answer });
            save();
          });
        }

        var reader = res.body.getReader();
        var decoder = new TextDecoder();
        var buffer = "";

        function read() {
          return reader.read().then(function (result) {
            if (result.done) {
              if (typing.parentNode) typing.remove();
              if (buffer.trim()) {
                var line = buffer.trim();
                if (line.indexOf("data: ") === 0) {
                  try {
                    var data = JSON.parse(line.slice(6));
                    if (data.type === "token") fullAnswer += data.token;
                  } catch (e) {}
                }
              }
              if (!botEl && !fullAnswer) {
                addMessage("assistant", "Jawab hasil karne mein waqt lag raha hai. Barah-e-karam dobara koshish karein.", null, false, [
                  { label: "Call Helpline: 0606-920247", url: "tel:0606920247", icon: "phone" },
                  { label: "Official WhatsApp", url: "https://wa.me/923078766389", icon: "whatsapp" },
                  { label: "Admissions Portal", url: "https://ul.edu.pk/page/How-to-Apply", icon: "portal" }
                ]);
              } else if (botEl && fullAnswer) {
                history.push({ role: "assistant", content: fullAnswer });
                save();
              }
              return;
            }

            buffer += decoder.decode(result.value, { stream: true });
            var blocks = buffer.split("\n\n");
            buffer = blocks.pop();

            blocks.forEach(function (block) {
              block.split("\n").forEach(function (line) {
                if (line.indexOf("data: ") !== 0) return;
                try {
                  var data = JSON.parse(line.slice(6));
                  if (data.type === "token") {
                    if (!botEl) {
                      if (typing.parentNode) typing.remove();
                      botEl = document.createElement("div");
                      botEl.className = "m bot";
                      botEl.setAttribute("dir", "auto");
                      log.appendChild(botEl);
                    }
                    fullAnswer += data.token;
                    botEl.innerHTML = render(fullAnswer);
                    log.scrollTop = log.scrollHeight;
                  } else if (data.type === "done") {
                    if (botEl) {
                      updateMessage(botEl, fullAnswer, data.sources, data.actions);
                    }
                    history.push({ role: "assistant", content: fullAnswer });
                    save();
                  } else if (data.type === "error") {
                    if (typing.parentNode) typing.remove();
                    addMessage("assistant", data.message || "Masla paish aaya.", null, true, [
                      { label: "Call Helpline: 0606-920247", url: "tel:0606920247", icon: "phone" },
                      { label: "Official WhatsApp", url: "https://wa.me/923078766389", icon: "whatsapp" }
                    ]);
                  }
                } catch (err) {
                  console.error(err);
                }
              });
            });
            return read();
          });
        }

        return read();
      })
      .catch(function (e) {
        clearTimeout(timer);
        if (typing.parentNode) typing.remove();
        history.pop();
        var errMsg = "Server tak rasai mein masla aaya. Dobara koshish karein ya helpline par rabta karein.";
        if (streamAborted || (e && e.name === "AbortError")) {
          errMsg = "Server jawab dene mein معمول se zyada waqt le raha hai. Barah-e-karam dobara poochhein:";
        } else if (e && e.message && e.message.indexOf("Failed to fetch") === -1) {
          errMsg = e.message;
        }
        var errEl = addMessage("assistant", errMsg, null, true, [
          { label: "Dobara Koshish Karein 🔄", url: "javascript:void(0)", icon: "portal" },
          { label: "Call Helpline: 0606-920247", url: "tel:0606920247", icon: "phone" },
          { label: "Official WhatsApp", url: "https://wa.me/923078766389", icon: "whatsapp" }
        ]);
        var retryBtn = errEl.querySelector('.act-btn[href="javascript:void(0)"]');
        if (retryBtn) {
          retryBtn.addEventListener("click", function (evt) {
            evt.preventDefault();
            errEl.remove();
            send(text);
          });
        }
      })
      .finally(function () {
        clearTimeout(timer);
        setBusy(false);
        input.focus();
      });
  }

  function open(v) {
    panel.hidden = !v;
    if (launchWrap) launchWrap.hidden = v;
    if (v) {
      if (callout) callout.style.display = "none";
      panel.classList.add("open");
      setTimeout(function () { input.focus(); }, 50);
    } else {
      panel.classList.remove("open");
      launch.focus();
    }
  }

  launch.addEventListener("click", function () { open(true); });
  if (callout) {
    callout.addEventListener("click", function () { open(true); });
    if (calloutClose) {
      calloutClose.addEventListener("click", function (e) {
        e.stopPropagation();
        callout.style.display = "none";
      });
    }
    setTimeout(function () {
      if (panel.hidden && history.length === 0) {
        callout.style.display = "flex";
      }
    }, 1600);
  }
  $(".close").addEventListener("click", function () { open(false); });
  $(".reset").addEventListener("click", function () { history = []; save(); start(); });
  panel.addEventListener("keydown", function (e) { if (e.key === "Escape") open(false); });
  form.addEventListener("submit", function (e) { e.preventDefault(); send(input.value); });
  input.addEventListener("keydown", function (e) {
    if (e.key === "Enter" && !e.shiftKey && !e.isComposing) { e.preventDefault(); send(input.value); }
  });
  input.addEventListener("input", function () {
    input.style.height = "auto"; input.style.height = Math.min(input.scrollHeight, 110) + "px";
  });

  var SpeechRec = window.SpeechRecognition || window.webkitSpeechRecognition;
  var recognition = null;
  var isListening = false;

  if (micBtn) {
    if (SpeechRec) {
      try {
        recognition = new SpeechRec();
        recognition.continuous = false;
        recognition.interimResults = true;
        recognition.lang = "ur-PK";

        recognition.onstart = function () {
          isListening = true;
          micBtn.classList.add("listening");
          micBtn.setAttribute("aria-label", "Suno raha hai... click karke stop karein");
          micBtn.setAttribute("title", "Suno raha hai... click karke stop karein");
        };

        recognition.onresult = function (event) {
          var transcript = "";
          for (var i = event.resultIndex; i < event.results.length; ++i) {
            transcript += event.results[i][0].transcript;
          }
          if (transcript) {
            input.value = transcript;
            input.style.height = "auto";
            input.style.height = Math.min(input.scrollHeight, 110) + "px";
          }
        };

        recognition.onerror = function () {
          stopListening();
        };

        recognition.onend = function () {
          stopListening();
        };

        function stopListening() {
          isListening = false;
          micBtn.classList.remove("listening");
          micBtn.setAttribute("aria-label", "Bol kar sawal poochein");
          micBtn.setAttribute("title", "Bol kar sawal poochein");
        }

        micBtn.addEventListener("click", function () {
          if (busy) return;
          if (isListening) {
            recognition.stop();
          } else {
            try {
              recognition.start();
            } catch (e) {
              stopListening();
            }
          }
        });
      } catch (e) {
        console.warn("SpeechRec init error:", e);
      }
    } else {
      micBtn.addEventListener("click", function () {
        alert("Voice typing ke liye barah-e-karam Google Chrome ya Microsoft Edge browser use karein (aapke browser mein Speech Recognition enable nahi hai).");
      });
    }
  }

  function mount() { document.body.appendChild(host); start(); }
  if (document.body) mount(); else document.addEventListener("DOMContentLoaded", mount);
})();
