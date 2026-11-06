// "Mr. Miyagi" - the canvas-drawn coach (a vector take on the logo mascot) who acts
// out whatever habit was just detected. Drawn with plain canvas primitives, no
// images, so it also shows up in the Picture-in-Picture window (which mirrors the
// main canvas). All shapes are in head-radius units: the context is scaled by r.
(function () {
  const TAU = Math.PI * 2;
  const FONT = `"Google Sans Flex", "Google Sans", Roboto, system-ui, sans-serif`;
  // Backdrop disc by state: idle blue, then green → yellow → red as a habit repeats (Google tonal 100s).
  const BACKDROP = ["#D3E3FD", "#C4EED0", "#FEEFC3", "#FAD2CF"];
  const C = {
    skin: "#F7BC9A", skinShade: "#EDA083", skinLine: "#D4795A", ear: "#E58E70", nose: "#F29A80",
    blush: "rgba(239, 108, 92, 0.32)", blushHot: "rgba(234, 67, 53, 0.42)", flush: "rgba(234, 67, 53, 0.16)",
    hair: "#FFFFFF", hairShade: "#D5DAEE",
    navy: "#1D2742", tongue: "#E8776B",
    robe: "#2F62D8", robeDark: "#2149AE", robeLight: "#4C7DEA",
    sweat: "#4285F4",
  };

  function circle(c, x, y, rad, fill) { c.beginPath(); c.arc(x, y, rad, 0, TAU); c.fillStyle = fill; c.fill(); }
  function oval(c, x, y, rx, ry, fill, rot = 0) { c.beginPath(); c.ellipse(x, y, rx, ry, rot, 0, TAU); c.fillStyle = fill; c.fill(); }
  function line(c, pts, w, color) {
    c.beginPath(); c.moveTo(pts[0], pts[1]);
    for (let i = 2; i < pts.length; i += 2) c.lineTo(pts[i], pts[i + 1]);
    c.lineWidth = w; c.strokeStyle = color; c.stroke();
  }

  // A fluffy white mass (beard, hair): a lavender pass a little lower, then a slightly
  // smaller white pass, so every puff gets a soft shaded rim.
  function fluff(c, blobs) {
    for (const [fill, dy, k] of [[C.hairShade, 0.045, 1], [C.hair, -0.01, 0.9]]) {
      c.beginPath();
      for (const [x, y, rad] of blobs) { c.moveTo(x + rad * k, y + dy); c.arc(x, y + dy, rad * k, 0, TAU); }
      c.fillStyle = fill; c.fill();
    }
  }
  const mirror = (list) => list.flatMap(([x, y, rad]) => (x ? [[-x, y, rad], [x, y, rad]] : [[x, y, rad]]));
  const TUFTS = mirror([[0.8, -0.42, 0.15], [0.91, -0.25, 0.18], [0.94, -0.04, 0.17]]);
  const BEARD = mirror([
    [0.8, -0.02, 0.16], [0.8, 0.2, 0.19], [0.71, 0.45, 0.21], [0.53, 0.68, 0.23], [0.28, 0.84, 0.25], [0, 0.9, 0.26],
    [0.44, 0.42, 0.27], [0.2, 0.58, 0.3], [0, 0.56, 0.33],
  ]);
  const MUSTACHE = mirror([[0.14, 0.24, 0.13], [0.31, 0.27, 0.12], [0.45, 0.31, 0.1]]);

  // [inner, control, outer] points of the right brow; the left one is mirrored.
  const BROWS = {
    normal:  [[0.12, -0.34], [0.28, -0.44], [0.44, -0.35]],
    angry:   [[0.1, -0.26], [0.27, -0.33], [0.45, -0.43]],
    raised:  [[0.12, -0.47], [0.28, -0.58], [0.44, -0.48]],
    worried: [[0.11, -0.43], [0.27, -0.42], [0.44, -0.32]],
  };
  const BROWS_FOR_EYES = { angry: "angry", wide: "raised", up: "raised", spiral: "raised", sleepy: "worried" };

  function brows(c, kind) {
    const b = BROWS[kind] || BROWS.normal;
    c.lineWidth = 0.1; c.strokeStyle = C.navy;
    for (const s of [-1, 1]) {
      c.beginPath(); c.moveTo(s * b[0][0], b[0][1]);
      c.quadraticCurveTo(s * b[1][0], b[1][1], s * b[2][0], b[2][1]); c.stroke();
    }
  }

  function eyes(c, kind, t, look) {
    const ey = -0.15;
    const blink = (kind === "normal" || kind === "angry") && t % 4 < 0.13;
    for (const s of [-1, 1]) {
      const x = s * 0.28;
      if (kind === "spiral") {
        c.beginPath();
        for (let a = 0; a < 10; a += 0.3) {
          const rr = (a / 10) * 0.12, ang = a + t * 8 * s;
          c.lineTo(x + Math.cos(ang) * rr, ey + Math.sin(ang) * rr);
        }
        c.lineWidth = 0.035; c.strokeStyle = C.navy; c.stroke(); continue;
      }
      if (blink) { line(c, [x - 0.08, ey, x + 0.08, ey], 0.045, C.navy); continue; }
      if (kind === "sleepy") { // heavy lids: lower half of the eye under a lid line
        c.beginPath(); c.ellipse(x, ey, 0.08, 0.075, 0, 0, Math.PI); c.fillStyle = C.navy; c.fill();
        line(c, [x - 0.1, ey, x + 0.1, ey], 0.04, C.navy); continue;
      }
      if (kind === "wide" || kind === "side" || kind === "up") { // whites show: alarm, or where he's looking
        const big = kind === "wide" ? 1.15 : 1;
        oval(c, x, ey, 0.13 * big, 0.15 * big, "#fff"); c.lineWidth = 0.03; c.strokeStyle = C.navy; c.stroke();
        const px = kind === "side" ? (Math.sin(t * 2) > 0 ? 0.055 : -0.055) : 0;
        const py = kind === "up" ? -0.06 : 0;
        oval(c, x + px, ey + py, 0.065 * big, 0.08 * big, C.navy);
        circle(c, x + px + 0.022, ey + py - 0.03, 0.022, "#fff"); continue;
      }
      // normal / angry: solid dark eyes with a glint, like the logo
      const [lx, ly] = look || [0, 0];
      oval(c, x + lx, ey + ly, 0.075, kind === "angry" ? 0.068 : 0.095, C.navy);
      circle(c, x + lx + 0.025, ey + ly - 0.03, 0.025, "#fff");
    }
  }

  function mouth(c, kind, t) {
    const y = 0.47;
    c.lineWidth = 0.055; c.strokeStyle = C.navy; c.beginPath();
    if (kind === "smile") { c.arc(0, y - 0.1, 0.12, 0.2 * Math.PI, 0.8 * Math.PI); c.stroke(); }
    else if (kind === "frown") { c.arc(0, y + 0.1, 0.11, 1.2 * Math.PI, 1.8 * Math.PI); c.stroke(); }
    else if (kind === "o") { oval(c, 0, y, 0.06 + Math.sin(t * 6) * 0.012, 0.08, C.navy); oval(c, 0, y + 0.045, 0.035, 0.02, C.tongue); }
    else if (kind === "flat") line(c, [-0.09, y, 0.09, y], 0.055, C.navy);
  }

  function sweat(c, t) {
    const x = 0.6, y = -0.5 + ((t * 0.5) % 0.35);
    c.beginPath(); c.moveTo(x, y - 0.13);
    c.bezierCurveTo(x + 0.03, y - 0.06, x + 0.08, y - 0.01, x + 0.08, y + 0.03);
    c.arc(x, y + 0.03, 0.08, 0, Math.PI);
    c.bezierCurveTo(x - 0.08, y - 0.01, x - 0.03, y - 0.06, x, y - 0.13);
    c.fillStyle = C.sweat; c.fill();
    circle(c, x - 0.025, y + 0.02, 0.022, "rgba(255,255,255,0.8)");
  }

  // The blue gi: shoulders, inner V, crossed lapels and sleeve folds. It runs past the
  // backdrop and gets clipped by it.
  function body(c) {
    c.beginPath();
    c.moveTo(-1.3, 2.7); c.lineTo(-1.22, 1.4);
    c.bezierCurveTo(-1.16, 1.0, -0.86, 0.88, -0.44, 0.86); c.lineTo(0.44, 0.86);
    c.bezierCurveTo(0.86, 0.88, 1.16, 1.0, 1.22, 1.4); c.lineTo(1.3, 2.7); c.closePath();
    c.fillStyle = C.robe; c.fill();
    c.beginPath(); c.moveTo(-0.4, 0.86); c.lineTo(0, 1.6); c.lineTo(0.4, 0.86); c.closePath();
    c.fillStyle = C.robeDark; c.fill();
    line(c, [0.48, 0.9, -0.06, 1.72], 0.15, C.robeLight);
    line(c, [-0.48, 0.9, 0.1, 1.85], 0.15, C.robeLight);
    line(c, [-0.98, 1.3, -0.94, 1.9], 0.04, C.robeDark);
    line(c, [0.98, 1.3, 0.94, 1.9], 0.04, C.robeDark);
  }

  // A hand on a gi sleeve. (x, y): palm centre; s: size; rot: radians (0 = fingers up, the
  // sleeve trails the other way); pose: "palm", "point" (index out) or "fist"; flip mirrors
  // it so the thumb faces the other side; sleeve: sleeve length in hand units (0 = none).
  function hand(c, x, y, s, rot, pose = "palm", flip = false, sleeve = 3.2) {
    c.save(); c.translate(x, y); c.rotate(rot); c.scale(flip ? -s : s, s);
    if (sleeve) { line(c, [0, 1, 0, sleeve], 1.12, C.robeDark); line(c, [0, 1, 0, sleeve], 0.98, C.robe); }
    const parts = [[0, 0.3, 0, -0.05, 0.92]];
    let thumb;
    if (pose === "palm") {
      parts.push([-0.36, -0.2, -0.39, -0.76, 0.19], [-0.12, -0.25, -0.13, -0.9, 0.19],
                 [0.12, -0.25, 0.13, -0.86, 0.19], [0.36, -0.2, 0.39, -0.66, 0.19]);
      thumb = [0.4, 0.2, 0.7, -0.18, 0.24];
    } else if (pose === "point") {
      parts.push([-0.28, -0.2, -0.3, -1.05, 0.22], [-0.05, -0.38, 0.32, -0.38, 0.3]);
      thumb = [0.36, 0.12, 0.05, -0.02, 0.22];
    } else {
      parts.push([-0.3, -0.4, 0.32, -0.4, 0.32]);
      thumb = [0.36, 0.12, -0.05, -0.02, 0.22];
    }
    // outline pass then fill pass: one silhouette, with thin gaps between the fingers
    for (const list of [parts, [thumb]]) {
      for (const [x1, y1, x2, y2, w] of list) line(c, [x1, y1, x2, y2], w + 0.09, C.skinLine);
      for (const [x1, y1, x2, y2, w] of list) line(c, [x1, y1, x2, y2], w, C.skin);
    }
    c.restore();
  }

  function crossedArms(c) {
    for (const s of [1, -1]) { // far arm first, near arm on top
      line(c, [-s * 1.05, 0.92, s * 0.62, 1.22], 0.4, C.robeDark);
      line(c, [-s * 1.05, 0.92, s * 0.62, 1.22], 0.33, C.robeLight);
      hand(c, s * 0.74, 1.2, 0.18, s * Math.PI / 2, "fist", s < 0, 0);
    }
  }

  function messyHair(c, t) {
    for (let i = -2; i <= 2; i++) {
      const x0 = i * 0.12, tx = i * 0.17 + Math.sin(t * 9 + i) * 0.06, ty = -1.24 + Math.abs(i) * 0.05;
      c.beginPath(); c.moveTo(x0, -0.9); c.quadraticCurveTo(x0 + 0.05, -1.08, tx, ty);
      c.lineWidth = 0.09; c.strokeStyle = C.hairShade; c.stroke();
      c.lineWidth = 0.05; c.strokeStyle = C.hair; c.stroke();
    }
  }

  // Text in head units. bubble: a speech bubble pointing at his head; otherwise haloed text.
  function label(c, R, text, x, y, size, bubble) {
    c.save(); c.scale(1 / R, 1 / R); x *= R; y *= R; size = Math.max(10, size * R);
    c.font = `700 ${size}px ${FONT}`; c.textAlign = "center"; c.textBaseline = "middle"; c.lineJoin = "round";
    if (bubble) {
      const w = c.measureText(text).width + size * 1.1, h = size * 1.75, lw = Math.max(1.5, size * 0.1), rr = h / 2;
      c.fillStyle = "#fff"; c.strokeStyle = C.navy; c.lineWidth = lw;
      const l = x - w / 2, tp = y - h / 2;
      c.beginPath(); c.moveTo(l + rr, tp);
      c.arcTo(l + w, tp, l + w, tp + h, rr); c.arcTo(l + w, tp + h, l, tp + h, rr);
      c.arcTo(l, tp + h, l, tp, rr); c.arcTo(l, tp, l + w, tp, rr); c.closePath();
      c.fill(); c.stroke();
      c.beginPath(); c.moveTo(x - size * 0.35, tp + h - lw); c.lineTo(x - size * 0.05, tp + h + size * 0.5);
      c.lineTo(x + size * 0.25, tp + h - lw); c.fill(); c.stroke();
    } else { c.strokeStyle = "#fff"; c.lineWidth = size * 0.22; c.strokeText(text, x, y); }
    c.fillStyle = C.navy; c.fillText(text, x, y + size * 0.04);
    c.restore();
  }

  // One entry per habit id: eyes, mouth, optional brows / look (normal-eye offset), body motion
  // (wobble, shake, tilt, squash, zoom, lift = neck stretch), alpha, sway (beard),
  // behind(c, t) drawn under the head, extra(c, t, lift) drawn on top, label / zzz.
  const MOODS = {
    idle:               { eyes: "normal", mouth: "smile" },
    beard_stroke:       { eyes: "angry", mouth: "flat", sway: 1,
                          extra: (c, t) => hand(c, 0.3, 0.74 + Math.sin(t * 5) * 0.14, 0.27, -0.35, "palm", true) },
    chin_touch:         { eyes: "normal", look: [0.035, -0.03], brows: "raised", mouth: "flat", tilt: 0.1,
                          extra: (c) => hand(c, 0.22, 1.0, 0.27, -0.45, "point", true) },
    face_touch:         { eyes: "wide", mouth: "o",
                          extra: (c) => { hand(c, -0.68, 0.14, 0.26, 0.28); hand(c, 0.68, 0.14, 0.26, -0.28, "palm", true); } },
    hand_to_mouth:      { eyes: "wide", mouth: "o", extra: (c) => hand(c, 0.06, 0.48, 0.27, -1.05, "palm", true) },
    neck_touch:         { eyes: "up", mouth: "o", lift: 0.7, zoom: 0.85,
                          extra: (c, t, lift) => hand(c, 0.3, 1.15 + lift * 0.4, 0.25, -0.3, "palm", true) },
    hair_touch:         { eyes: "up", mouth: "flat",
                          extra: (c, t) => { messyHair(c, t); hand(c, 0.6, -0.72 + Math.sin(t * 8) * 0.04, 0.25, -0.3, "palm", true, 7.5); } },
    excessive_movement: { eyes: "spiral", mouth: "o", wobble: 0.3 },
    looking_away:       { eyes: "side", mouth: "flat", label: "📷 look here!" },
    slouching:          { eyes: "sleepy", mouth: "frown", squash: 0.72, zzz: true },
    leaning_in:         { eyes: "wide", mouth: "o", zoom: 1.35 },
    frowning:           { eyes: "angry", mouth: "frown", label: (t) => t % 2 > 1 && "smile 🙂" },
    out_of_frame:       { eyes: "wide", mouth: "o", alpha: 0.35, label: "?" },
    fidgeting:          { eyes: "wide", mouth: "flat", shake: 1,
                          extra: (c, t) => { hand(c, -0.92 + Math.sin(t * 25) * 0.08, 0.72, 0.26, -0.3, "fist");
                                             hand(c, 0.92 + Math.cos(t * 23) * 0.08, 0.72, 0.26, 0.3, "fist", true); } },
    arms_crossed:       { eyes: "angry", mouth: "flat", extra: crossedArms },
  };

  // cx, cy: head centre; r: head radius (px); mood: condition id or "idle"; t: seconds;
  // severity 1..3 tints the backdrop and, at 3, flushes the face and adds a sweat drop.
  function drawAvatar(ctx, cx, cy, r, mood, t, severity) {
    const active = mood !== "idle" && mood in MOODS;
    const m = active ? MOODS[mood] : MOODS.idle;
    const sev = active ? Math.max(1, Math.min(3, severity || 1)) : 0;
    const by = cy + r * 0.2, br = r * 1.5;
    ctx.save();
    circle(ctx, cx, by, br, BACKDROP[sev]);
    // The gi ends at the backdrop's rim; above its centre anything may overflow (labels, a stretched neck).
    ctx.beginPath(); ctx.rect(cx - r * 5, cy - r * 6, r * 10, r * 6.2);
    ctx.moveTo(cx + br, by); ctx.arc(cx, by, br, 0, TAU); ctx.clip();

    ctx.globalAlpha = m.alpha ?? 1;
    let x = cx, y = cy + Math.sin(t * 2) * r * 0.03;
    if (m.wobble) x += Math.sin(t * 7) * r * m.wobble;
    if (m.shake) { x += (Math.random() - 0.5) * r * 0.12; y += (Math.random() - 0.5) * r * 0.12; }
    ctx.translate(x, y);
    if (m.wobble) ctx.rotate(Math.sin(t * 7) * 0.3);
    if (m.tilt) ctx.rotate(m.tilt);
    const zoom = (m.zoom || 1) * (1 + (sev ? 0.03 * Math.sin(t * 10) * sev : 0));
    ctx.scale(zoom * r, zoom * r * (m.squash || 1));
    ctx.lineCap = "round"; ctx.lineJoin = "round";

    const lift = (m.lift || 0) * (1 + 0.3 * Math.sin(t * 3));
    if (lift) { // stretched neck, tucked into the collar
      line(ctx, [0, 0.95, 0, 0.55 - lift], 0.46, C.skinLine);
      line(ctx, [0, 0.95, 0, 0.55 - lift], 0.4, C.skin);
      line(ctx, [0.1, 0.9, 0.1, 0.62 - lift], 0.07, C.skinShade);
    }
    body(ctx);
    if (m.behind) m.behind(ctx, t);
    ctx.translate(0, -lift);

    // head: hair tufts and ears behind, then the bald dome with a rim shade and highlight
    fluff(ctx, TUFTS);
    for (const s of [-1, 1]) { circle(ctx, s * 0.8, -0.1, 0.14, C.skinShade); oval(ctx, s * 0.82, -0.1, 0.07, 0.09, C.ear); }
    oval(ctx, 0.04, -0.02, 0.78, 0.9, C.skinShade);
    oval(ctx, -0.01, -0.07, 0.76, 0.87, C.skin);
    oval(ctx, -0.32, -0.6, 0.2, 0.1, "rgba(255,255,255,0.35)", -0.6);
    if (sev >= 3) oval(ctx, 0, -0.05, 0.78, 0.9, C.flush);
    for (const s of [-1, 1]) oval(ctx, s * 0.5, 0.04, 0.12, 0.07, sev >= 2 ? C.blushHot : C.blush);
    brows(ctx, m.brows || BROWS_FOR_EYES[m.eyes]);
    eyes(ctx, m.eyes, t, m.look);

    // beard (swaying while it's being stroked), mustache, nose, mouth
    const sway = m.sway ? Math.sin(t * 5) * 0.04 : 0;
    fluff(ctx, sway ? BEARD.map(([bx, bY, rad]) => [bx + sway * (bY + 0.1), bY, rad]) : BEARD);
    fluff(ctx, MUSTACHE);
    oval(ctx, 0, 0.1, 0.11, 0.085, C.nose);
    oval(ctx, -0.035, 0.07, 0.035, 0.022, "rgba(255,255,255,0.5)");
    mouth(ctx, m.mouth, t);
    if (sev >= 3) sweat(ctx, t);

    if (m.extra) m.extra(ctx, t, lift);
    const text = typeof m.label === "function" ? m.label(t) : m.label;
    if (text === "?") label(ctx, r, "?", 0, -1.3, 0.65, false);
    else if (text) label(ctx, r, text, 0, -1.36, 0.28, true);
    if (m.zzz) label(ctx, r, "z z z", 0.85, -0.95 - ((t * 0.6) % 0.35), 0.25, false);
    ctx.restore();
  }

  window.drawAvatar = drawAvatar;
  window.AVATAR_MOODS = Object.keys(MOODS);
})();
