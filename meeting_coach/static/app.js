// Meeting Coach front-end: camera capture, WebSocket to the Python vision
// backend, and all visual cues (box, mask, border, avatar, toast, sound).
(() => {
  const $ = (id) => document.getElementById(id);
  const view = $("view"), vctx = view.getContext("2d");
  const avatarCanvas = $("avatar"), actx = avatarCanvas.getContext("2d");
  const cam = $("cam"), pipVideo = $("pipVideo");
  const STORE_KEY = "meetingCoach.settings.v1";

  const S = {
    defaults: [], focusArea: "", conditions: {}, styles: [], modes: [],
    mirror: true, sound: false, debug: false, fps: 12,
    ws: null, running: false, paused: false, awaiting: false, sentAt: 0, lastSend: 0,
    result: null, toast: null, counts: {}, latency: 0, personal: null, teachActive: false,
  };

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
    const res = await fetch("/api/conditions").then((r) => r.json());
    S.defaults = res.conditions; S.focusArea = res.focus_area; S.styles = res.styles; S.modes = res.modes; S.personal = res.personal;
    const saved = load();
    for (const c of res.conditions) S.conditions[c.id] = { ...c, ...(saved.conditions?.[c.id] || {}), focus: c.focus };
    for (const k of ["mirror", "sound", "debug", "fps"]) if (k in saved) S[k] = saved[k];
    $("optMirror").checked = S.mirror; $("optSound").checked = S.sound; $("optDebug").checked = S.debug; $("optFps").value = S.fps;
    renderConditions(); renderCounts(); renderTeach();
    startTicker();
  }

  // ---------------------------------------------------------------- settings UI
  function renderConditions() {
    const root = $("conditions"); root.innerHTML = "";
    const focusBox = document.createElement("section");
    focusBox.innerHTML = `<h3>🎯 Focus: ${S.focusArea}</h3>`;
    const more = document.createElement("details");
    const extras = Object.values(S.conditions).filter((c) => !c.focus);
    more.innerHTML = `<summary>More habits (${extras.filter((c) => c.enabled).length}/${extras.length} on): tick to enable</summary>`;
    more.open = extras.some((c) => c.enabled);
    root.append(focusBox, more);
    for (const c of Object.values(S.conditions)) {
      const el = document.createElement("div");
      el.className = "cond" + (c.enabled ? "" : " off");
      const trained = S.personal?.classes?.includes(c.id);
      el.innerHTML = `
        <div class="head"><input type="checkbox" ${c.enabled ? "checked" : ""} data-k="enabled">
          <span>${c.emoji} ${c.label}</span><span class="needs">${c.needs}${trained ? " · 🧠" : ""}</span></div>
        <div class="body">
          <span>Sensitivity</span><input type="range" min="0" max="100" value="${c.sensitivity}" data-k="sensitivity">
          <span>Hold (s)</span><input type="number" min="0" max="30" step="0.1" value="${c.min_duration}" data-k="min_duration">
          <span>Cooldown (s)</span><input type="number" min="0" max="120" step="0.5" value="${c.cooldown}" data-k="cooldown">
          <span>Detect with</span><select data-k="mode">${S.modes.map((m) => `<option ${m === c.mode ? "selected" : ""}>${m}</option>`).join("")}</select>
          <span>Cues</span><div class="styles">${S.styles.map((s) => `<label><input type="checkbox" data-style="${s}" ${c.styles.includes(s) ? "checked" : ""}> ${s}</label>`).join("")}</div>
        </div>`;
      el.addEventListener("input", (ev) => {
        const t = ev.target;
        if (t.dataset.style) {
          const set = new Set(c.styles); t.checked ? set.add(t.dataset.style) : set.delete(t.dataset.style); c.styles = [...set];
        } else if (t.dataset.k === "enabled") { c.enabled = t.checked; el.classList.toggle("off", !c.enabled); renderCounts(); }
        else if (t.dataset.k === "mode") c.mode = t.value;
        else if (t.dataset.k) c[t.dataset.k] = Number(t.value);
        save(); sendConfig();
      });
      (c.focus ? focusBox : more).appendChild(el);
    }
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
      setStatus("camera blocked", "err"); $("hint").textContent = "Camera access failed: " + e.message; return;
    }
    S.running = true;
    $("btnStart").disabled = true;
    for (const id of ["btnPause", "btnCalibrate", "btnPip", "btnReport", "btnTeach", "btnTrain", "btnTeachClear"]) $(id).disabled = false;
    $("hint").textContent = "Sit naturally for 3 seconds while we calibrate your baseline posture.";
    connect();
  }

  function connect() {
    const ws = new WebSocket(`${location.protocol === "https:" ? "wss" : "ws"}://${location.host}/ws`);
    ws.binaryType = "arraybuffer";
    S.ws = ws; S.awaiting = false;
    setStatus("connecting…");
    ws.onopen = () => { setStatus("live", "live"); sendConfig(); send({ type: "status" }); };
    ws.onclose = () => { setStatus("reconnecting…", "err"); if (S.running) setTimeout(connect, 1500); };
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
      renderCounts();
      setStatus(`live · ${Math.round(S.latency)} ms`, "live");
    } else if (msg.type === "report") showReport(msg);
    else if (msg.type === "trained") onTrained(msg);
    else if (msg.type === "personal") { S.personal = msg.personal; renderTeach(); renderConditions(); }
    else if (msg.type === "error") { console.warn(msg.message); $("hint").textContent = "⚠️ " + msg.message; }
  }

  function onNewAlert(a) {
    if (a.styles.includes("toast")) S.toast = { text: `${a.emoji} ${a.label} — ${a.tip}`, until: performance.now() + 5000, severity: a.severity };
    if (a.styles.includes("sound") && S.sound) beep(a.severity);
    const li = document.createElement("li");
    li.textContent = `${clock(S.result?.elapsed || 0)}  ${a.emoji} ${a.label}${a.severity > 1 ? " ×" + a.count : ""}`;
    $("log").prepend(li);
    while ($("log").children.length > 50) $("log").lastChild.remove();
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

  function renderCounts() {
    const ul = $("counts"); ul.innerHTML = "";
    const rows = Object.values(S.conditions).filter((c) => c.enabled).map((c) => [c, S.counts[c.id] || 0]).sort((a, b) => b[1] - a[1]);
    for (const [c, n] of rows) {
      const li = document.createElement("li");
      li.innerHTML = `<span>${c.emoji} ${c.label}</span><b>${n}</b>`;
      ul.appendChild(li);
    }
  }

  // ---------------------------------------------------------------- teach mode
  function renderTeach() {
    const sel = $("teachLabel");
    const current = sel.value;
    sel.innerHTML = `<option value="neutral">😐 Neutral (sitting normally)</option>` +
      Object.values(S.conditions).map((c) => `<option value="${c.id}">${c.emoji} ${c.label}</option>`).join("");
    if (current) sel.value = current;
    const ul = $("teachCounts"); ul.innerHTML = "";
    for (const [label, n] of Object.entries(S.personal?.counts || {})) {
      const c = S.conditions[label];
      const li = document.createElement("li");
      li.innerHTML = `<span>${c ? c.emoji + " " + c.label : "😐 Neutral"}</span><b>${n}</b>`;
      ul.appendChild(li);
    }
    const m = S.personal?.metrics;
    $("trainStatus").textContent = S.personal?.ready
      ? `Model ready: ${S.personal.classes.join(", ")}. Hold-out accuracy ${m?.holdout_accuracy == null ? "n/a" : Math.round(m.holdout_accuracy * 100) + "%"}.`
      : "No personal model yet.";
  }

  function onTeach(t) {
    S.teachActive = !t.done;
    $("teachStatus").textContent = t.done ? `Recorded ${t.samples} samples of "${t.label}".` : `Recording "${t.label}"… ${t.remaining}s (${t.samples} samples)`;
    if (t.done) send({ type: "status" });
  }

  function onTrained(msg) {
    S.personal = msg.personal;
    $("trainStatus").textContent = msg.ok ? "" : "⚠️ " + msg.error;
    if (msg.ok) renderTeach();
    renderConditions();
  }

  // ---------------------------------------------------------------- report
  function showReport(msg) {
    $("reportBody").innerHTML = markdown(msg.markdown || "");
    $("reportSource").textContent = `Written by: ${msg.source}${msg.note ? " — " + msg.note : ""}`;
  }

  function markdown(md) {
    const esc = (s) => s.replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
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
  const PRIORITY = ["face_touch", "hand_to_mouth", "beard_stroke", "chin_touch", "neck_touch", "hair_touch", "excessive_movement",
    "fidgeting", "out_of_frame", "looking_away", "frowning", "slouching", "leaning_in", "arms_crossed"];

  function topAlert(style) {
    const alerts = (S.result?.alerts || []).filter((a) => !style || a.styles.includes(style));
    alerts.sort((a, b) => PRIORITY.indexOf(a.id) - PRIORITY.indexOf(b.id));
    return alerts[0];
  }

  function render(now) {
    const t = now / 1000;
    const vw = cam.videoWidth || 16, vh = cam.videoHeight || 9;
    const W = 960, H = Math.round((W * vh) / vw);
    if (view.width !== W || view.height !== H) { view.width = W; view.height = H; }
    const c = vctx;
    c.save(); c.fillStyle = "#000"; c.fillRect(0, 0, W, H);
    if (cam.videoWidth) {
      c.save();
      if (S.mirror) { c.translate(W, 0); c.scale(-1, 1); }
      c.drawImage(cam, 0, 0, W, H);
      c.restore();
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
          c.lineWidth = 3 + a.severity * 2; c.strokeStyle = `rgba(229,72,77,${0.5 + 0.5 * pulse})`;
          roundRect(c, b.x, b.y, b.w, b.h, 12); c.stroke();
          chip(c, `${a.emoji} ${a.label}`, b.x, Math.max(0, b.y - 30));
        }
        if (a.styles.includes("mask") && (r.face_box || a.box)) {
          const b = box(r.face_box || a.box);
          const size = Math.max(b.w, b.h) * (0.9 + 0.1 * pulse);
          c.save(); c.globalAlpha = 0.92; c.font = `${size}px system-ui, "Apple Color Emoji", "Segoe UI Emoji", sans-serif`;
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
          grad.addColorStop(0, `rgba(229,72,77,${0.35 + 0.45 * k})`); grad.addColorStop(1, "rgba(229,72,77,0)");
          c.fillStyle = grad; c.fillRect(x, y, w, h);
        }
      }
    }

    // corner avatar (also visible in the pop-out window)
    const av = live ? topAlert("avatar") : null;
    c.fillStyle = "rgba(255,255,255,0.75)"; roundRect(c, W - 150, H - 150, 136, 136, 20); c.fill();
    window.drawAvatar(c, W - 82, H - 92, 34, av ? av.id : "idle", t, av?.severity);

    // toast
    if (S.toast && now < S.toast.until && live) {
      c.font = "600 18px system-ui, sans-serif";
      const text = S.toast.text, tw = Math.min(c.measureText(text).width + 32, W - 190);
      c.fillStyle = S.toast.severity >= 3 ? "rgba(229,72,77,0.92)" : "rgba(29,34,48,0.88)";
      roundRect(c, 16, H - 64, tw, 44, 12); c.fill();
      c.fillStyle = "#fff"; c.textBaseline = "middle"; c.textAlign = "left";
      fitText(c, text, 32, H - 42, tw - 32);
    }

    // banners
    let banner = null;
    if (!S.running) banner = "Camera off";
    else if (S.paused) banner = "⏸ Paused";
    else if (S.teachActive) banner = `⏺ ${$("teachStatus").textContent}`;
    else if (r?.calibrating) banner = "🎚 Calibrating… sit naturally";
    if (banner) {
      c.font = "700 22px system-ui, sans-serif"; c.textAlign = "center"; c.textBaseline = "middle";
      const bw = c.measureText(banner).width + 40;
      c.fillStyle = "rgba(29,34,48,0.8)"; roundRect(c, (W - bw) / 2, 16, bw, 44, 12); c.fill();
      c.fillStyle = "#fff"; c.fillText(banner, W / 2, 38);
    }
    c.restore();

    // sidebar avatar
    const aw = avatarCanvas.width, ah = avatarCanvas.height;
    actx.clearRect(0, 0, aw, ah);
    window.drawAvatar(actx, aw / 2, ah / 2 - 10, 58, av ? av.id : "idle", t, av?.severity);
    actx.font = "600 14px system-ui, sans-serif"; actx.textAlign = "center"; actx.fillStyle = getComputedStyle(document.body).color;
    actx.fillText(av ? `${av.emoji} ${av.label}` : S.running ? "All good 👍" : "Hi! I'm Coachy", aw / 2, ah - 12);
  }

  function drawDebug(c, d, box, W, H) {
    c.save(); c.lineWidth = 1.5; c.font = "12px monospace";
    const colors = { hair: "#a78bfa", face: "#60a5fa", mouth: "#f472b6", beard: "#fbbf24", neck: "#34d399" };
    for (const [name, z] of Object.entries(d.zones || {})) {
      const b = box(z); c.strokeStyle = colors[name] || "#fff"; c.setLineDash([5, 4]); c.strokeRect(b.x, b.y, b.w, b.h);
      c.fillStyle = colors[name] || "#fff"; c.fillText(name, b.x + 3, b.y + 12);
    }
    c.setLineDash([]); c.fillStyle = "#22d3ee";
    for (const hand of d.hands || []) for (const [x, y] of hand) { c.beginPath(); c.arc((S.mirror ? 1 - x : x) * W, y * H, 3, 0, 7); c.fill(); }
    if (d.head) { c.fillStyle = "#fff"; c.fillText(`yaw ${d.head.yaw} pitch ${d.head.pitch} gaze ${d.head.gaze} ${d.head.fresh ? "" : "(memory)"}`, 10, H - 80); }
    if (S.result?.learned) c.fillText("learned " + JSON.stringify(S.result.learned), 10, H - 96);
    c.restore();
  }

  function roundRect(c, x, y, w, h, r) { c.beginPath(); c.roundRect ? c.roundRect(x, y, w, h, r) : c.rect(x, y, w, h); }
  function chip(c, text, x, y) {
    c.font = "600 16px system-ui, sans-serif";
    const w = c.measureText(text).width + 18;
    c.fillStyle = "rgba(229,72,77,0.92)"; roundRect(c, x, y, w, 26, 8); c.fill();
    c.fillStyle = "#fff"; c.textAlign = "left"; c.textBaseline = "middle"; c.fillText(text, x + 9, y + 13);
  }
  function fitText(c, text, x, y, max) {
    let s = text; while (s.length > 4 && c.measureText(s).width > max) s = s.slice(0, -2);
    c.fillText(s === text ? s : s + "…", x, y);
  }
  const clock = (s) => `${String(Math.floor(s / 60)).padStart(2, "0")}:${String(Math.floor(s % 60)).padStart(2, "0")}`;
  function setStatus(text, cls) { const el = $("status"); el.textContent = text; el.className = "pill " + (cls || ""); }

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
    } catch (e) { $("hint").textContent = "Pop-out not supported in this browser: " + e.message; }
  }

  document.querySelectorAll(".tabs button").forEach((b) => b.addEventListener("click", () => {
    document.querySelectorAll(".tabs button").forEach((x) => x.classList.toggle("active", x === b));
    document.querySelectorAll(".tab").forEach((x) => x.classList.toggle("hidden", x.id !== "tab-" + b.dataset.tab));
  }));
  $("btnStart").onclick = start;
  $("btnPause").onclick = () => { S.paused = !S.paused; $("btnPause").textContent = S.paused ? "▶ Resume" : "⏸ Pause"; };
  $("btnCalibrate").onclick = () => send({ type: "calibrate" });
  $("btnPip").onclick = popOut;
  $("btnReport").onclick = () => { $("reportBody").textContent = "Generating your coaching report…"; $("reportSource").textContent = ""; $("reportDlg").showModal(); send({ type: "report" }); };
  $("btnNewSession").onclick = () => { send({ type: "reset" }); S.counts = {}; $("log").innerHTML = ""; renderCounts(); };
  $("btnTeach").onclick = () => send({ type: "teach", label: $("teachLabel").value, seconds: Number($("teachSeconds").value) });
  $("btnTrain").onclick = () => { $("trainStatus").textContent = "Training…"; send({ type: "train" }); };
  $("btnTeachClear").onclick = () => { if (confirm("Delete all recorded teach samples and the personal model?")) send({ type: "teach_clear", label: null }); };
  $("btnResetDefaults").onclick = () => { for (const c of S.defaults) S.conditions[c.id] = { ...c, styles: [...c.styles] }; save(); renderConditions(); sendConfig(); };
  $("optMirror").onchange = (e) => { S.mirror = e.target.checked; save(); };
  $("optSound").onchange = (e) => { S.sound = e.target.checked; save(); if (S.sound) beep(1); };
  $("optDebug").onchange = (e) => { S.debug = e.target.checked; save(); sendConfig(); };
  $("optFps").onchange = (e) => { S.fps = Math.min(30, Math.max(2, Number(e.target.value) || 12)); save(); };

  init().catch((e) => { setStatus("error", "err"); $("hint").textContent = "Failed to load: " + e.message; });
})();
