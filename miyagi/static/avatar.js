// "Coachy" - a little canvas-drawn character that acts out whatever habit
// was just detected. Drawn with plain canvas primitives so it also shows up in
// the Picture-in-Picture window (which mirrors the main canvas).
(function () {
  // Google palette (tonal 300s): idle blue, then green → yellow → red as a habit repeats.
  const IDLE = "#8AB4F8";
  const SKIN = ["#81C995", "#FDD663", "#F28B82"]; // severity 1..3
  const INK = "#1F1F1F";

  function circle(ctx, x, y, r, fill, stroke) {
    ctx.beginPath(); ctx.arc(x, y, r, 0, Math.PI * 2);
    if (fill) { ctx.fillStyle = fill; ctx.fill(); }
    if (stroke) { ctx.strokeStyle = stroke; ctx.stroke(); }
  }

  function eyes(ctx, r, kind, t) {
    const ex = r * 0.36, ey = -r * 0.12, er = r * 0.16;
    const blink = kind === "normal" && (t % 4) < 0.12;
    for (const s of [-1, 1]) {
      const x = s * ex;
      if (kind === "spiral") {
        ctx.beginPath();
        for (let a = 0; a < 10; a += 0.3) {
          const rr = (a / 10) * er, ang = a + t * 8 * s;
          ctx.lineTo(x + Math.cos(ang) * rr, ey + Math.sin(ang) * rr);
        }
        ctx.stroke(); continue;
      }
      if (kind === "sleepy" || blink) {
        ctx.beginPath(); ctx.moveTo(x - er, ey); ctx.quadraticCurveTo(x, ey + er * 0.6, x + er, ey); ctx.stroke(); continue;
      }
      const big = kind === "wide" ? 1.35 : 1;
      circle(ctx, x, ey, er * big, "#fff", INK);
      let px = 0, py = 0;
      if (kind === "side") px = Math.sin(t * 2) > 0 ? er * 0.55 : -er * 0.55;
      if (kind === "up") py = -er * 0.5;
      circle(ctx, x + px, ey + py, er * 0.45 * big, INK);
      if (kind === "angry") {
        ctx.beginPath(); ctx.moveTo(x - s * er * 1.3, ey - er * 1.9); ctx.lineTo(x + s * er * 0.9, ey - er * 1.1); ctx.stroke();
      }
    }
  }

  function mouth(ctx, r, kind, t) {
    const y = r * 0.35, w = r * 0.32;
    ctx.beginPath();
    if (kind === "smile") { ctx.arc(0, y - w * 0.6, w, 0.2 * Math.PI, 0.8 * Math.PI); ctx.stroke(); }
    else if (kind === "frown") { ctx.arc(0, y + w * 0.9, w, 1.2 * Math.PI, 1.8 * Math.PI); ctx.stroke(); }
    else if (kind === "o") { circle(ctx, 0, y, w * 0.38 + Math.sin(t * 6) * 2, INK); }
    else if (kind === "flat") { ctx.moveTo(-w * 0.7, y); ctx.lineTo(w * 0.7, y); ctx.stroke(); }
    else if (kind === "zip") {
      ctx.moveTo(-w, y); ctx.lineTo(w, y); ctx.stroke();
      for (let i = -w; i <= w; i += w / 4) { ctx.beginPath(); ctx.moveTo(i, y - 4); ctx.lineTo(i, y + 4); ctx.stroke(); }
    }
  }

  function hand(ctx, x, y, s) {
    ctx.save(); ctx.translate(x, y);
    circle(ctx, 0, 0, s, "#ffd9b3", INK);
    for (let i = -1.5; i <= 1.5; i += 1) circle(ctx, i * s * 0.55, -s * 0.95, s * 0.32, "#ffd9b3", INK);
    ctx.restore();
  }

  function label(ctx, text, x, y, size, color) {
    ctx.font = `600 ${size}px "Google Sans Flex", "Google Sans", Roboto, system-ui, sans-serif`; ctx.textAlign = "center"; ctx.textBaseline = "middle";
    ctx.fillStyle = color || INK; ctx.fillText(text, x, y);
  }

  const MOODS = {
    idle:               { eyes: "normal", mouth: "smile" },
    face_touch:         { eyes: "wide", mouth: "o", extra: (c, r, t) => { hand(c, -r * 0.85, r * 0.1, r * 0.22); hand(c, r * 0.85, r * 0.1, r * 0.22); } },
    hand_to_mouth:      { eyes: "wide", mouth: "zip", extra: (c, r, t) => hand(c, 0, r * 0.45, r * 0.26) },
    beard_stroke:       { eyes: "angry", mouth: "flat", extra: (c, r, t) => {
                            c.fillStyle = "#7a4a2a"; c.beginPath(); c.moveTo(-r * 0.75, r * 0.15);
                            c.quadraticCurveTo(0, r * 1.7 + Math.sin(t * 3) * 6, r * 0.75, r * 0.15);
                            c.quadraticCurveTo(0, r * 0.75, -r * 0.75, r * 0.15); c.fill();
                            hand(c, r * 0.35, r * 0.9 + Math.sin(t * 6) * r * 0.15, r * 0.22); } },
    neck_touch:         { eyes: "up", mouth: "o", lift: 0.55, extra: (c, r, t, lift) => hand(c, r * 0.45, r + lift * 0.5, r * 0.22) },
    hair_touch:         { eyes: "up", mouth: "flat", extra: (c, r, t) => {
                            c.strokeStyle = "#5b3a1e"; c.lineWidth = 4;
                            for (let i = -3; i <= 3; i++) { c.beginPath(); c.moveTo(i * r * 0.18, -r * 0.92);
                              c.lineTo(i * r * 0.25 + Math.sin(t * 9 + i) * 8, -r * 1.35); c.stroke(); }
                            c.lineWidth = 2.5; c.strokeStyle = INK; hand(c, r * 0.6, -r * 1.05, r * 0.2); } },
    chin_touch:         { eyes: "sleepy", mouth: "flat", tilt: 0.25, extra: (c, r) => hand(c, r * 0.2, r * 1.05, r * 0.24) },
    excessive_movement: { eyes: "spiral", mouth: "o", wobble: 0.35 },
    looking_away:       { eyes: "side", mouth: "flat", extra: (c, r) => label(c, "📷 look here!", 0, -r * 1.35, r * 0.28) },
    slouching:          { eyes: "sleepy", mouth: "frown", squash: 0.7, extra: (c, r, t) => label(c, "z z z", r * 0.9, -r * 0.9 - (t * 10 % 12), r * 0.25) },
    leaning_in:         { eyes: "wide", mouth: "o", zoom: 1.35 },
    frowning:           { eyes: "angry", mouth: "frown", extra: (c, r, t) => (t % 2 > 1) && label(c, "smile 🙂", 0, -r * 1.35, r * 0.28) },
    out_of_frame:       { eyes: "wide", mouth: "o", alpha: 0.35, extra: (c, r) => label(c, "?", 0, -r * 1.4, r * 0.7) },
    fidgeting:          { eyes: "wide", mouth: "flat", shake: 1, extra: (c, r, t) => { hand(c, -r * 1.1 + Math.sin(t * 25) * 6, r * 0.8, r * 0.2); hand(c, r * 1.1 + Math.cos(t * 23) * 6, r * 0.8, r * 0.2); } },
    arms_crossed:       { eyes: "angry", mouth: "flat", extra: (c, r) => {
                            c.lineWidth = r * 0.18; c.strokeStyle = "#ffd9b3"; c.lineCap = "round";
                            c.beginPath(); c.moveTo(-r * 0.9, r * 0.75); c.lineTo(r * 0.7, r * 1.05); c.stroke();
                            c.beginPath(); c.moveTo(r * 0.9, r * 0.75); c.lineTo(-r * 0.7, r * 1.05); c.stroke(); } },
  };

  // cx, cy: centre; r: head radius; mood: condition id or "idle"; t: seconds.
  function drawAvatar(ctx, cx, cy, r, mood, t, severity) {
    const m = MOODS[mood] || MOODS.idle;
    const sev = Math.max(1, Math.min(3, severity || 1));
    ctx.save();
    ctx.globalAlpha = m.alpha ?? 1;
    let x = cx, y = cy + Math.sin(t * 2) * r * 0.04;
    if (m.wobble) x += Math.sin(t * 7) * r * m.wobble;
    if (m.shake) { x += (Math.random() - 0.5) * 6; y += (Math.random() - 0.5) * 6; }
    ctx.translate(x, y);
    if (m.wobble) ctx.rotate(Math.sin(t * 7) * 0.3);
    if (m.tilt) ctx.rotate(m.tilt);
    const zoom = (m.zoom || 1) * (1 + (mood !== "idle" ? 0.04 * Math.sin(t * 10) * sev : 0));
    ctx.scale(zoom, zoom * (m.squash || 1));

    // body + (optional) giraffe neck
    const lift = (m.lift || 0) * r * (1 + 0.3 * Math.sin(t * 3));
    ctx.lineWidth = 2.5; ctx.strokeStyle = INK;
    ctx.fillStyle = mood === "idle" ? IDLE : SKIN[sev - 1];
    ctx.beginPath(); ctx.ellipse(0, r * 1.25, r * 0.9, r * 0.45, 0, Math.PI, 0); ctx.fill(); ctx.stroke();
    if (lift) {
      ctx.fillStyle = "#FBBC04"; ctx.fillRect(-r * 0.22, r * 0.6 - lift, r * 0.44, lift + r * 0.3);
      ctx.strokeRect(-r * 0.22, r * 0.6 - lift, r * 0.44, lift + r * 0.3);
      ctx.fillStyle = "#a0662b";
      for (let i = 0; i < 3; i++) circle(ctx, (i % 2 ? 1 : -1) * r * 0.08, r * 0.7 - lift + i * lift / 3, r * 0.06, "#a0662b");
      ctx.translate(0, -lift);
    }
    circle(ctx, 0, 0, r, mood === "idle" ? IDLE : SKIN[sev - 1], INK);
    if (sev >= 3 && mood !== "idle") { // sweat drop when it keeps happening
      ctx.fillStyle = "#4285F4"; ctx.beginPath(); ctx.ellipse(r * 0.8, -r * 0.5 + (t * 20 % 15), r * 0.08, r * 0.13, 0, 0, Math.PI * 2); ctx.fill();
    }
    ctx.lineWidth = 2.5; ctx.strokeStyle = INK;
    eyes(ctx, r, m.eyes, t);
    mouth(ctx, r, m.mouth, t);
    if (m.extra) { ctx.lineWidth = 2.5; ctx.strokeStyle = INK; m.extra(ctx, r, t, lift); }
    ctx.restore();
  }

  window.drawAvatar = drawAvatar;
})();
