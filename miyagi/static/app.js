// Miyagi front-end: camera capture, WebSocket to the Python vision
// backend, and all visual cues (box, mask, border, avatar, toast, sound).
// UI follows Material Design 3 (see style.css); canvas cues use Google colors.
(() => {
  const $ = (id) => document.getElementById(id);
  const view = $("view"), vctx = view.getContext("2d");
  const avatarCanvas = $("avatar"), actx = avatarCanvas?.getContext("2d");
  // Coach-only mode (/coach): just the camera and cues; settings come from the full UI (localStorage).
  const COACH = document.body.dataset.mode === "coach";
  const cam = $("cam"), pipVideo = $("pipVideo");
  const STORE_KEY = "miyagi.settings.v1";

  // Google brand colors + M3 inverse surface for on-video elements.
  const G = { blue: "#4285F4", red: "#EA4335", yellow: "#FBBC04", green: "#34A853", purple: "#A142F4", cyan: "#24C1E0" };
  const INVERSE = "rgba(48,48,48,0.94)", ON_INVERSE = "#F2F2F2";
  const FONT = '"Google Sans Flex", "Google Sans", Roboto, system-ui, sans-serif';
  const ICON_FONT = '"Material Symbols Rounded"';
  const STYLE_LABELS = { box: "Box", mask: "Emoji mask", border: "Border", avatar: "Coachy", toast: "Tip", sound: "Sound" };
  const MODE_LABELS = { rules: "Rules", learned: "Learned", either: "Either" };

  const S = {
    defaults: [], focusArea: "", conditions: {}, styles: [], modes: [],
    mirror: true, sound: false, debug: false, fps: 12,
    ws: null, running: false, paused: false, awaiting: false, sentAt: 0, lastSend: 0,
    result: null, toast: null, counts: {}, latency: 0, personal: null, teachActive: false, logEmpty: true, calibratedOnce: false,
  };

  // The Miyagi mascot (logo), shown on the canvas while the camera is off.
  const mascot = new Image();
  mascot.src = "/static/brand/miyagi-192.png";

  const esc = (s) => String(s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));

  // ---------------------------------------------------------------- storage
  function load() { try { return JSON.parse(localStorage.getItem(STORE_KEY)) || {}; } catch { return {}; } }
  function save() {
    try {
      const conditions = {};
      for (const [id, c] of Object.entries(S.conditions))
        conditions[id] = { enabled: c.enabled, sensitivity: c.sensitivity, min_duration: c.min_duration, cooldown: c.cooldown, styles: c.styles, mode: c.mode };
      localStorage.setItem(STORE_KEY, JSON.stringify({ conditions, mirror: S.mirror, sound: S.sound, debug: S.debug, fps: S.fps }));
    } catch { /* storage unavailable: settings just won't persist */ }
  }

  // ---------------------------------------------------------------- init
  async function init() {
    const fontsReady = Promise.all([
      document.fonts.load(`500 16px ${FONT}`), document.fonts.load(`24px ${ICON_FONT}`, "videocam"),
    ]).catch(() => {});
    const res = await fetch("/api/conditions").then((r) => r.json());
    S.defaults = res.conditions; S.focusArea = res.focus_area; S.styles = res.styles; S.modes = res.modes; S.personal = res.personal;
    const saved = load();
    for (const c of res.conditions) S.conditions[c.id] = { ...c, ...(saved.conditions?.[c.id] || {}), focus: c.focus };
    for (const k of ["mirror", "sound", "debug", "fps"]) if (k in saved) S[k] = saved[k];
    if (!COACH) {
      $("optMirror").checked = S.mirror; $("optSound").checked = S.sound; $("optDebug").checked = S.debug; $("optFps").value = S.fps;
      renderConditions(); renderCounts(); renderTeach();
    }
    await fontsReady;
    startTicker();
    if (COACH) {
      notice("keyboard", "P pop out · C calibrate · Space pause · F full screen · M mirror", 7000);
      start();
    }
  }

  // ---------------------------------------------------------------- settings UI
  function condCard(c) {
    const el = document.createElement("div");
    el.className = "cond" + (c.enabled ? "" : " off");
    const trained = S.personal?.classes?.includes(c.id);
    const pct = (v) => `--pct:${v}%`;
    el.innerHTML = `
      <div class="cond-head">
        <span class="emoji" aria-hidden="true">${c.emoji}</span>
        <div class="grow">
          <div class="title-small">${esc(c.label)}</div>
          <div class="body-small">${c.focus ? `<span class="focus-tag"><span class="icon">center_focus_strong</span>Focus</span> ` : ""}needs ${esc(c.needs)}${trained ? " · personal model ✓" : ""}</div>
        </div>
        <label class="switch" title="Enable"><input type="checkbox" role="switch" data-k="enabled" ${c.enabled ? "checked" : ""} aria-label="Enable ${esc(c.label)}"><span class="track"></span><span class="handle"></span></label>
      </div>
      <div class="cond-body">
        <div class="field-row"><span class="label-medium">Sensitivity</span>
          <input type="range" min="0" max="100" value="${c.sensitivity}" data-k="sensitivity" style="${pct(c.sensitivity)}" aria-label="Sensitivity">
          <span class="value" data-v="sensitivity">${c.sensitivity}</span></div>
        <div class="field-row"><span class="label-medium">Hold</span>
          <input type="range" min="0" max="5" step="0.1" value="${c.min_duration}" data-k="min_duration" style="${pct((c.min_duration / 5) * 100)}" aria-label="Hold seconds">
          <span class="value" data-v="min_duration">${c.min_duration}s</span></div>
        <div class="field-row"><span class="label-medium">Cooldown</span>
          <input type="range" min="0" max="30" step="0.5" value="${c.cooldown}" data-k="cooldown" style="${pct((c.cooldown / 30) * 100)}" aria-label="Cooldown seconds">
          <span class="value" data-v="cooldown">${c.cooldown}s</span></div>
        <div><div class="label-medium" style="margin-bottom:6px">Detect with</div>
          <div class="segmented" role="radiogroup">${S.modes.map((m) => `
            <label><input type="radio" name="mode-${c.id}" value="${m}" data-k="mode" ${m === c.mode ? "checked" : ""}
              ${m !== "rules" && !trained ? "disabled" : ""}><span class="icon">check</span>${MODE_LABELS[m] || m}</label>`).join("")}
          </div></div>
        <div><div class="label-medium" style="margin-bottom:6px">Cues</div>
          <div class="chips">${S.styles.map((s) => `
            <label class="chip"><input type="checkbox" data-style="${s}" ${c.styles.includes(s) ? "checked" : ""}><span class="icon">check</span>${STYLE_LABELS[s] || s}</label>`).join("")}
          </div></div>
      </div>`;
    el.addEventListener("input", (ev) => {
      const t = ev.target;
      if (t.dataset.style) {
        const set = new Set(c.styles); t.checked ? set.add(t.dataset.style) : set.delete(t.dataset.style); c.styles = [...set];
      } else if (t.dataset.k === "enabled") {
        c.enabled = t.checked; el.classList.toggle("off", !c.enabled); renderCounts(); updateMoreSummary();
      } else if (t.dataset.k === "mode") c.mode = t.value;
      else if (t.dataset.k) {
        c[t.dataset.k] = Number(t.value);
        t.style.setProperty("--pct", `${((t.value - t.min) / (t.max - t.min)) * 100}%`);
        const out = el.querySelector(`[data-v="${t.dataset.k}"]`);
        if (out) out.textContent = t.dataset.k === "sensitivity" ? t.value : `${t.value}s`;
      }
      save(); sendConfig();
    });
    return el;
  }

  function updateMoreSummary() {
    const extras = Object.values(S.conditions).filter((c) => !c.focus);
    const el = document.querySelector("details.more .count");
    if (el) el.textContent = `${extras.filter((c) => c.enabled).length} of ${extras.length} on`;
  }

  function renderConditions() {
    if (COACH) return;
    const root = $("conditions"); root.innerHTML = "";
    const head = document.createElement("div");
    head.className = "section-label label-large"; head.style.marginTop = "8px";
    head.textContent = `Focus: ${S.focusArea}`;
    const focusBox = document.createElement("div");
    const more = document.createElement("details");
    more.className = "more";
    const extras = Object.values(S.conditions).filter((c) => !c.focus);
    more.innerHTML = `<summary><span class="title-small" style="flex:1">More habits</span><span class="body-small count"></span><span class="icon">expand_more</span></summary><div></div>`;
    more.open = extras.some((c) => c.enabled);
    root.append(head, focusBox, more);
    for (const c of Object.values(S.conditions)) (c.focus ? focusBox : more.lastChild).appendChild(condCard(c));
    updateMoreSummary();
  }

  function configPayload() {
    const conditions = {};
    for (const [id, c] of Object.entries(S.conditions))
      conditions[id] = { enabled: c.enabled, sensitivity: c.sensitivity, min_duration: c.min_duration, cooldown: c.cooldown, styles: c.styles, mode: c.mode };
    return { type: "config", conditions, debug: S.debug };
  }
  function send(obj) { if (S.ws?.readyState === 1) S.ws.send(JSON.stringify(obj)); }
  function sendConfig() { send(configPayload()); }

  // ---------------------------------------------------------------- camera + socket
  async function start() {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ video: { width: { ideal: 1280 }, height: { ideal: 720 } }, audio: false });
      cam.srcObject = stream; await cam.play();
    } catch (e) {
      setStatus("Camera blocked", "err"); snackbar("Camera access failed: " + e.message); return;
    }
    S.running = true;
    if (!COACH) {
      $("btnStart").disabled = true;
      for (const id of ["btnPause", "btnCalibrate", "btnPip", "btnReport", "btnTeach", "btnTrain", "btnTeachClear"]) $(id).disabled = false;
    }
    setHint("Sit naturally for 3 seconds while we calibrate your baseline posture.");
    connect();
  }

  function connect() {
    const ws = new WebSocket(`${location.protocol === "https:" ? "wss" : "ws"}://${location.host}/ws`);
    ws.binaryType = "arraybuffer";
    S.ws = ws; S.awaiting = false;
    setStatus("Connecting…", "busy");
    ws.onopen = () => { setStatus("Live", "live"); sendConfig(); send({ type: "status" }); };
    ws.onclose = () => { setStatus("Reconnecting…", "err"); if (S.running) setTimeout(connect, 1500); };
    ws.onmessage = (ev) => onMessage(JSON.parse(ev.data));
  }

  const grab = document.createElement("canvas");
  async function sendFrame(now) {
    if (!S.ws || S.ws.readyState !== 1 || S.paused || !cam.videoWidth) return;
    if (S.awaiting && now - S.sentAt < 3000) return; // one frame in flight (watchdog after 3 s)
    if (now - S.lastSend < 1000 / S.fps) return;
    S.lastSend = now; S.awaiting = true; S.sentAt = now;
    const w = 640, h = Math.round((640 * cam.videoHeight) / cam.videoWidth);
    grab.width = w; grab.height = h;
    grab.getContext("2d").drawImage(cam, 0, 0, w, h);
    const blob = await new Promise((r) => grab.toBlob(r, "image/jpeg", 0.75));
    if (!blob) { S.awaiting = false; return; }
    const jpeg = new Uint8Array(await blob.arrayBuffer());
    const buf = new Uint8Array(8 + jpeg.length);
    new DataView(buf.buffer).setFloat64(0, now, true);
    buf.set(jpeg, 8);
    if (S.ws.readyState === 1) S.ws.send(buf.buffer); else S.awaiting = false;
  }

  // ---------------------------------------------------------------- messages
  function onMessage(msg) {
    if (msg.type === "result") {
      S.awaiting = false;
      S.latency = performance.now() - S.sentAt;
      S.result = msg;
      S.counts = msg.counts;
      for (const a of msg.alerts) if (a.new) onNewAlert(a);
      if (msg.teach) onTeach(msg.teach);
      if (msg.calibrated && !S.calibratedOnce) {
        S.calibratedOnce = true;
        setHint("Coaching is live. Click Pop out to keep Coachy next to your call. Frames never leave this device.");
      }
      renderCounts();
      setStatus(`Live · ${Math.round(S.latency)} ms`, "live");
    } else if (msg.type === "report") showReport(msg);
    else if (msg.type === "trained") onTrained(msg);
    else if (msg.type === "personal") { S.personal = msg.personal; renderTeach(); renderConditions(); }
    else if (msg.type === "error") { console.warn(msg.message); snackbar(msg.message); }
  }

  function onNewAlert(a) {
    if (a.styles.includes("toast")) S.toast = { emoji: a.emoji, title: a.label, text: a.tip, until: performance.now() + 5000, severity: a.severity };
    if (a.styles.includes("sound") && S.sound) beep(a.severity);
    const log = $("log");
    if (!log) return;
    if (S.logEmpty) { log.innerHTML = ""; S.logEmpty = false; }
    const li = document.createElement("li");
    li.innerHTML = `<time>${clock(S.result?.elapsed || 0)}</time><span class="emoji">${a.emoji}</span><span class="grow body-medium">${esc(a.label)}</span>` +
      (a.severity > 1 ? `<span class="badge hot">×${a.count}</span>` : "");
    log.prepend(li);
    while (log.children.length > 50) log.lastChild.remove();
  }

  let audio;
  function beep(sev) {
    try {
      audio = audio || new AudioContext();
      const o = audio.createOscillator(), g = audio.createGain();
      o.frequency.value = 520 + sev * 120; o.type = "sine";
      g.gain.setValueAtTime(0.0001, audio.currentTime);
      g.gain.exponentialRampToValueAtTime(0.08, audio.currentTime + 0.02);
      g.gain.exponentialRampToValueAtTime(0.0001, audio.currentTime + 0.25);
      o.connect(g).connect(audio.destination); o.start(); o.stop(audio.currentTime + 0.3);
    } catch { /* audio unavailable */ }
  }

  let lastCountsKey = "";
  function renderCounts() {
    if (COACH) return;
    const rows = Object.values(S.conditions).filter((c) => c.enabled).map((c) => [c, S.counts[c.id] || 0]).sort((a, b) => b[1] - a[1]);
    const key = rows.map(([c, n]) => c.id + n).join();
    if (key === lastCountsKey) return;
    lastCountsKey = key;
    $("counts").innerHTML = rows.length
      ? rows.map(([c, n]) => `<li><span class="emoji">${c.emoji}</span><span class="grow body-medium">${esc(c.label)}</span><span class="badge${n >= 3 ? " hot" : ""}">${n}</span></li>`).join("")
      : `<li class="empty body-small">No habits enabled. Turn some on in Habits.</li>`;
  }

  // ---------------------------------------------------------------- teach mode
  function renderTeach() {
    if (COACH) return;
    const sel = $("teachLabel");
    const current = sel.value;
    sel.innerHTML = `<option value="neutral">😐 Neutral (sitting normally)</option>` +
      Object.values(S.conditions).map((c) => `<option value="${c.id}">${c.emoji} ${esc(c.label)}</option>`).join("");
    if (current) sel.value = current;
    const counts = Object.entries(S.personal?.counts || {});
    $("teachCounts").innerHTML = counts.length
      ? counts.map(([label, n]) => {
          const c = S.conditions[label];
          return `<li><span class="emoji">${c ? c.emoji : "😐"}</span><span class="grow body-medium">${c ? esc(c.label) : "Neutral"}</span><span class="badge">${n}</span></li>`;
        }).join("")
      : `<li class="empty body-small">No samples recorded yet.</li>`;
    const m = S.personal?.metrics;
    $("trainStatus").textContent = S.personal?.ready
      ? `Model ready: ${S.personal.classes.join(", ")} · hold-out accuracy ${m?.holdout_accuracy == null ? "n/a" : Math.round(m.holdout_accuracy * 100) + "%"}`
      : "No personal model yet.";
  }

  function onTeach(t) {
    if (COACH) return;
    S.teachActive = !t.done;
    const btn = $("btnTeach");
    btn.classList.toggle("recording", !t.done);
    btn.lastChild.textContent = t.done ? "Record" : `${t.remaining}s`;
    $("teachStatus").textContent = t.done ? `Recorded ${t.samples} samples of "${t.label}".` : `Recording "${t.label}"… ${t.remaining}s (${t.samples} samples)`;
    if (t.done) send({ type: "status" });
  }

  function onTrained(msg) {
    if (COACH) return;
    S.personal = msg.personal;
    if (msg.ok) renderTeach(); else $("trainStatus").textContent = msg.error;
    if (!msg.ok) snackbar(msg.error);
    renderConditions();
  }

  // ---------------------------------------------------------------- report
  function showReport(msg) {
    $("reportBody").innerHTML = markdown(msg.markdown || "");
    $("reportSource").textContent = `Written by ${msg.source}${msg.note ? " · " + msg.note : ""}`;
  }

  function markdown(md) {
    const inline = (s) => esc(s).replace(/\*\*(.+?)\*\*/g, "<b>$1</b>").replace(/\*(.+?)\*/g, "<i>$1</i>");
    let html = "", inList = false;
    for (const raw of md.split("\n")) {
      const line = raw.trimEnd();
      const li = line.match(/^\s*(?:[-*]|\d+\.)\s+(.*)/);
      if (li) { if (!inList) { html += "<ul>"; inList = true; } html += `<li>${inline(li[1])}</li>`; continue; }
      if (inList) { html += "</ul>"; inList = false; }
      const h = line.match(/^(#{1,4})\s+(.*)/);
      if (h) html += `<h${h[1].length + 1}>${inline(h[2])}</h${h[1].length + 1}>`;
      else if (line) html += `<p>${inline(line)}</p>`;
    }
    return html + (inList ? "</ul>" : "");
  }

  // ---------------------------------------------------------------- rendering
  const PRIORITY = ["beard_stroke", "chin_touch", "face_touch", "hand_to_mouth", "neck_touch", "hair_touch", "excessive_movement",
    "fidgeting", "out_of_frame", "looking_away", "frowning", "slouching", "leaning_in", "arms_crossed"];

  function topAlert(style) {
    const alerts = (S.result?.alerts || []).filter((a) => !style || a.styles.includes(style));
    alerts.sort((a, b) => PRIORITY.indexOf(a.id) - PRIORITY.indexOf(b.id));
    return alerts[0];
  }

  const rgba = (hex, a) => { const n = parseInt(hex.slice(1), 16); return `rgba(${n >> 16},${(n >> 8) & 255},${n & 255},${a})`; };

  function render(now) {
    const t = now / 1000;
    const vw = cam.videoWidth || 16, vh = cam.videoHeight || 9;
    const W = 960, H = Math.round((W * vh) / vw);
    if (view.width !== W || view.height !== H) { view.width = W; view.height = H; }
    const c = vctx;
    c.save(); c.fillStyle = "#131314"; c.fillRect(0, 0, W, H);
    if (cam.videoWidth) {
      c.save();
      if (S.mirror) { c.translate(W, 0); c.scale(-1, 1); }
      c.drawImage(cam, 0, 0, W, H);
      c.restore();
    }
    if (!S.running && mascot.complete && mascot.naturalWidth) {
      const m = Math.min(W, H) * 0.42;
      c.drawImage(mascot, (W - m) / 2, (H - m) / 2 + 12, m, m);
    }
    const box = (b, pad = 0) => b && ({ x: (S.mirror ? 1 - b.x - b.w : b.x) * W - pad, y: b.y * H - pad, w: b.w * W + 2 * pad, h: b.h * H + 2 * pad });
    const r = S.result;
    const live = S.running && !S.paused && r;

    if (live && S.debug && r.debug) drawDebug(c, r.debug, box, W, H);

    if (live) {
      for (const a of r.alerts) {
        const pulse = 0.55 + 0.45 * Math.sin(t * (6 + a.severity * 2));
        if (a.styles.includes("box") && a.box) {
          const b = box(a.box, 6);
          c.lineWidth = 2 + a.severity * 2; c.strokeStyle = rgba(G.red, 0.55 + 0.45 * pulse);
          roundRect(c, b.x, b.y, b.w, b.h, 16); c.stroke();
          chip(c, a.emoji, a.label, b.x, Math.max(4, b.y - 40));
        }
        if (a.styles.includes("mask") && (r.face_box || a.box)) {
          const b = box(r.face_box || a.box);
          const size = Math.max(b.w, b.h) * (0.9 + 0.1 * pulse);
          c.save(); c.globalAlpha = 0.94; c.font = `${size}px "Noto Color Emoji", "Apple Color Emoji", "Segoe UI Emoji", sans-serif`;
          c.textAlign = "center"; c.textBaseline = "middle";
          c.translate(b.x + b.w / 2, b.y + b.h / 2); c.rotate(Math.sin(t * 5) * 0.12);
          c.fillText(a.emoji, 0, 0); c.restore();
        }
      }
      const border = topAlert("border");
      if (border) {
        const k = 0.5 + 0.5 * Math.sin(t * 6);
        const g = 20 + border.severity * 12;
        for (const [x, y, w, h, gx0, gy0, gx1, gy1] of [[0, 0, W, g, 0, 0, 0, g], [0, H - g, W, g, 0, H, 0, H - g], [0, 0, g, H, 0, 0, g, 0], [W - g, 0, g, H, W, 0, W - g, 0]]) {
          const grad = c.createLinearGradient(gx0, gy0, gx1, gy1);
          grad.addColorStop(0, rgba(G.red, 0.35 + 0.45 * k)); grad.addColorStop(1, rgba(G.red, 0));
          c.fillStyle = grad; c.fillRect(x, y, w, h);
        }
      }
    }

    // corner Coachy (also visible in the pop-out window)
    const av = live ? topAlert("avatar") : null;
    c.fillStyle = "rgba(240,244,249,0.92)"; roundRect(c, W - 148, H - 148, 132, 132, 28); c.fill();
    window.drawAvatar(c, W - 82, H - 90, 34, av ? av.id : "idle", t, av?.severity);

    // toast: M3 snackbar on the video
    if (S.toast && now < S.toast.until && live) {
      const accent = S.toast.severity >= 3 ? G.red : S.toast.severity === 2 ? G.yellow : G.blue;
      const maxW = W - 196;
      c.font = `500 16px ${FONT}`;
      const title = `${S.toast.emoji}  ${S.toast.title}`;
      c.font = `400 14px ${FONT}`;
      const tw = Math.min(Math.max(c.measureText(S.toast.text).width, 200) + 48, maxW);
      const x = 16, y = H - 84;
      c.fillStyle = INVERSE; roundRect(c, x, y, tw, 68, 8); c.fill();
      c.fillStyle = accent; roundRect(c, x, y, 6, 68, [8, 0, 0, 8]); c.fill();
      c.fillStyle = ON_INVERSE; c.textAlign = "left"; c.textBaseline = "middle";
      c.font = `500 16px ${FONT}`; fitText(c, title, x + 22, y + 22, tw - 40);
      c.font = `400 14px ${FONT}`; c.fillStyle = "rgba(242,242,242,0.8)"; fitText(c, S.toast.text, x + 22, y + 46, tw - 40);
    }

    // status banner: M3-style pill with a Material Symbol
    let banner = null;
    if (S.notice && now < S.notice.until) banner = [S.notice.icon, S.notice.text];
    else if (!S.running) banner = ["videocam_off", "Camera off"];
    else if (S.paused) banner = ["pause", "Paused"];
    else if (S.teachActive) banner = ["fiber_manual_record", $("teachStatus").textContent];
    else if (r?.calibrating) banner = ["center_focus_strong", "Calibrating… sit naturally"];
    if (banner) {
      c.font = `500 16px ${FONT}`;
      const bw = c.measureText(banner[1]).width + 64;
      const bx = (W - bw) / 2;
      c.fillStyle = INVERSE; roundRect(c, bx, 16, bw, 44, 22); c.fill();
      c.font = `22px ${ICON_FONT}`; c.textAlign = "left"; c.textBaseline = "middle";
      c.fillStyle = S.teachActive ? G.red : "#A8C7FA"; c.fillText(banner[0], bx + 16, 39);
      c.font = `500 16px ${FONT}`; c.fillStyle = ON_INVERSE; c.fillText(banner[1], bx + 46, 39);
    }
    c.restore();

    // sidebar Coachy (full UI only)
    if (!actx) return;
    const aw = avatarCanvas.width, ah = avatarCanvas.height;
    actx.clearRect(0, 0, aw, ah);
    window.drawAvatar(actx, aw / 2, ah / 2 - 6, 62, av ? av.id : "idle", t, av?.severity);
    const label = av ? `${av.emoji} ${av.label}` : S.running ? "All good 👍" : "Hi! I'm Coachy";
    if ($("coachyLabel").textContent !== label) $("coachyLabel").textContent = label;
  }

  function drawDebug(c, d, box, W, H) {
    c.save(); c.lineWidth = 1.5; c.font = `500 12px "Roboto Mono", monospace`;
    const colors = { hair: G.purple, face: G.blue, mouth: G.red, beard: G.yellow, neck: G.green };
    for (const [name, z] of Object.entries(d.zones || {})) {
      const b = box(z); c.strokeStyle = colors[name] || "#fff"; c.setLineDash([6, 4]); c.strokeRect(b.x, b.y, b.w, b.h);
      c.fillStyle = colors[name] || "#fff"; c.fillText(name, b.x + 4, b.y + 14);
    }
    c.setLineDash([]); c.fillStyle = G.cyan;
    for (const hand of d.hands || []) for (const [x, y] of hand) { c.beginPath(); c.arc((S.mirror ? 1 - x : x) * W, y * H, 3, 0, 7); c.fill(); }
    c.fillStyle = "#fff";
    if (d.head) c.fillText(`yaw ${d.head.yaw} pitch ${d.head.pitch} gaze ${d.head.gaze} ${d.head.fresh ? "" : "(memory)"}`, 12, 80);
    if (S.result?.learned) c.fillText("learned " + JSON.stringify(S.result.learned), 12, 96);
    c.restore();
  }

  function roundRect(c, x, y, w, h, r) { c.beginPath(); c.roundRect ? c.roundRect(x, y, w, h, r) : c.rect(x, y, w, h); }
  function chip(c, emoji, text, x, y) {
    c.font = `500 15px ${FONT}`;
    const label = `${emoji}  ${text}`;
    const w = c.measureText(label).width + 24;
    c.fillStyle = G.red; roundRect(c, x, y, w, 32, 8); c.fill();
    c.fillStyle = "#fff"; c.textAlign = "left"; c.textBaseline = "middle"; c.fillText(label, x + 12, y + 17);
  }
  function fitText(c, text, x, y, max) {
    let s = text; while (s.length > 4 && c.measureText(s).width > max) s = s.slice(0, -2);
    c.fillText(s === text ? s : s + "…", x, y);
  }
  const clock = (s) => `${String(Math.floor(s / 60)).padStart(2, "0")}:${String(Math.floor(s % 60)).padStart(2, "0")}`;

  function setHint(text) { const el = $("hint"); if (el) el.textContent = text; }
  function notice(icon, text, ms = 6000) { S.notice = { icon, text, until: performance.now() + ms }; }

  function setStatus(text, cls) {
    const el = $("status");
    if (!el) return;
    el.className = "assist-chip " + (cls || "");
    el.querySelector(".txt").textContent = text;
  }

  let snackTimer;
  function snackbar(text) {
    const el = $("snackbar");
    if (!el) { notice("warning", text, 8000); return; }
    el.querySelector(".txt").textContent = text;
    el.classList.add("show");
    clearTimeout(snackTimer);
    snackTimer = setTimeout(() => el.classList.remove("show"), 6000);
  }

  // A Worker-driven clock keeps capture + drawing alive when the tab is in the
  // background (requestAnimationFrame stops there) - essential, because during
  // a meeting the coach lives in the pop-out window, not the focused tab.
  function startTicker() {
    const src = "setInterval(() => postMessage(0), 33);";
    const worker = new Worker(URL.createObjectURL(new Blob([src], { type: "text/javascript" })));
    worker.onmessage = () => { const now = performance.now(); render(now); if (S.running) sendFrame(now); };
  }

  // ---------------------------------------------------------------- buttons
  async function popOut() {
    try {
      if (document.pictureInPictureElement) { await document.exitPictureInPicture(); return; }
      if (!pipVideo.srcObject) pipVideo.srcObject = view.captureStream(15);
      await pipVideo.play();
      await pipVideo.requestPictureInPicture();
    } catch (e) { snackbar("Pop-out isn't supported in this browser: " + e.message); }
  }

  function togglePause() {
    S.paused = !S.paused;
    const b = $("btnPause");
    if (b) b.innerHTML = S.paused ? `<span class="icon">play_arrow</span><span class="label">Resume</span>` : `<span class="icon">pause</span><span class="label">Pause</span>`;
    setStatus(S.paused ? "Paused" : "Live", S.paused ? "busy" : "live");
  }

  function toggleFullscreen() {
    if (document.fullscreenElement) document.exitFullscreen().catch(() => {});
    else document.documentElement.requestFullscreen().catch(() => {});
  }

  if (COACH) {
    // No visible controls: keyboard shortcuts only (keypresses also count as the user
    // gesture that Picture-in-Picture and full screen require).
    document.addEventListener("keydown", (e) => {
      if (e.ctrlKey || e.metaKey || e.altKey) return;
      const k = e.key.toLowerCase();
      if (k === "p") popOut();
      else if (k === "c") { send({ type: "calibrate" }); notice("center_focus_strong", "Calibrating… sit naturally", 3000); }
      else if (k === " ") { e.preventDefault(); togglePause(); }
      else if (k === "f") toggleFullscreen();
      else if (k === "m") { S.mirror = !S.mirror; save(); }
      else if (k === "?" || k === "h") notice("keyboard", "P pop out · C calibrate · Space pause · F full screen · M mirror", 6000);
    });
    view.addEventListener("dblclick", toggleFullscreen);
  } else {
    document.querySelectorAll(".tab-btn").forEach((b) => b.addEventListener("click", () => {
      document.querySelectorAll(".tab-btn").forEach((x) => x.setAttribute("aria-selected", String(x === b)));
      document.querySelectorAll(".tab-panel").forEach((x) => { x.hidden = x.id !== "tab-" + b.dataset.tab; });
    }));
    $("btnStart").onclick = start;
    $("btnPause").onclick = togglePause;
    $("btnCalibrate").onclick = () => send({ type: "calibrate" });
    $("btnPip").onclick = popOut;
    $("btnReport").onclick = () => { $("reportBody").innerHTML = `<p>Generating your coaching report…</p>`; $("reportSource").textContent = ""; $("reportDlg").showModal(); send({ type: "report" }); };
    $("btnNewSession").onclick = () => { send({ type: "reset" }); S.counts = {}; S.logEmpty = true; $("log").innerHTML = `<li class="empty body-small">Nothing yet. Nice!</li>`; lastCountsKey = ""; renderCounts(); };
    $("btnTeach").onclick = () => send({ type: "teach", label: $("teachLabel").value, seconds: Number($("teachSeconds").value) });
    $("btnTrain").onclick = () => { $("trainStatus").textContent = "Training…"; send({ type: "train" }); };
    $("btnTeachClear").onclick = () => { if (confirm("Delete all recorded teach samples and the personal model?")) send({ type: "teach_clear", label: null }); };
    $("btnResetDefaults").onclick = () => { for (const c of S.defaults) S.conditions[c.id] = { ...c, styles: [...c.styles] }; save(); renderConditions(); lastCountsKey = ""; renderCounts(); sendConfig(); };
    $("optMirror").onchange = (e) => { S.mirror = e.target.checked; save(); };
    $("optSound").onchange = (e) => { S.sound = e.target.checked; save(); if (S.sound) beep(1); };
    $("optDebug").onchange = (e) => { S.debug = e.target.checked; save(); sendConfig(); };
    $("optFps").onchange = (e) => { S.fps = Math.min(30, Math.max(2, Number(e.target.value) || 12)); save(); };
  }

  init().catch((e) => { setStatus("Error", "err"); snackbar("Failed to load: " + e.message); });
})();
