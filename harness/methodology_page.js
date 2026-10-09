// Interactive charts for docs/methodology.html. Inlined into the page by harness/methodology.py.
// Data comes from #meth-data (computed from the logs); all visible text from #meth-labels.
(() => {
  "use strict";
  const DATA = JSON.parse(document.getElementById("meth-data").textContent);
  const L = JSON.parse(document.getElementById("meth-labels").textContent);
  const NS = "http://www.w3.org/2000/svg";
  const DS = DATA.datasets;

  // ---------- helpers ----------
  const tpl = (s, o) => s.replace(/\{(\w+)\}/g, (_, k) => (k in o ? o[k] : ""));
  const fmt = (v, nd = 2) => (v === Infinity ? L.units.inf : Number.isFinite(v) ? v.toFixed(nd) : "–");
  function S(tag, attrs, parent) {
    const e = document.createElementNS(NS, tag);
    for (const [k, v] of Object.entries(attrs || {})) if (v !== null && v !== undefined) e.setAttribute(k, v);
    if (parent) parent.appendChild(e);
    return e;
  }
  function H(tag, attrs, text) {
    const e = document.createElement(tag);
    for (const [k, v] of Object.entries(attrs || {})) if (v !== null && v !== undefined) e.setAttribute(k, v);
    if (text !== undefined && text !== null) e.textContent = text;
    return e;
  }
  function T(parent, attrs, text) {
    const t = S("text", attrs, parent);
    t.textContent = text;
    return t;
  }
  function niceTicks(lo, hi, n) {
    if (!(hi > lo)) hi = lo + 1;
    const raw = (hi - lo) / (n || 5);
    const mag = Math.pow(10, Math.floor(Math.log10(raw)));
    const r = raw / mag;
    const step = (r >= 7.5 ? 10 : r >= 3.5 ? 5 : r >= 1.5 ? 2 : 1) * mag;
    const out = [];
    for (let v = Math.ceil(lo / step - 1e-9) * step; v <= hi + 1e-9; v += step) out.push(+v.toPrecision(12));
    return out;
  }
  const css = (name) => `var(--${name})`;
  // Charts are drawn at the container's real width so text stays at its CSS size on phones.
  const widthOf = (el) => Math.max(320, Math.min(760, Math.round(el.clientWidth || 760)));
  const renderers = [];
  let resizeTimer = null;
  let lastWidth = window.innerWidth;
  window.addEventListener("resize", () => {
    if (Math.abs(window.innerWidth - lastWidth) < 8) return;
    lastWidth = window.innerWidth;
    clearTimeout(resizeTimer);
    resizeTimer = setTimeout(() => renderers.forEach((f) => f()), 150);
  });

  // ---------- tooltip (one for the page) ----------
  const tip = H("div", { class: "tip", role: "status" });
  tip.hidden = true;
  document.body.appendChild(tip);
  function lineKey(color, dash, shape) {
    const k = S("svg", { width: 20, height: 10, viewBox: "0 0 20 10", "aria-hidden": "true" });
    if (shape === "circle") S("circle", { cx: 10, cy: 5, r: 4, style: `fill:${color}` }, k);
    else if (shape === "square") S("rect", { x: 6, y: 1, width: 8, height: 8, rx: 1.5, style: `fill:${color}` }, k);
    else S("line", { x1: 0, x2: 20, y1: 5, y2: 5, style: `stroke:${color};stroke-width:2;stroke-linecap:round;${dash ? "stroke-dasharray:5 3" : ""}` }, k);
    return k;
  }
  function showTip(clientX, clientY, title, rows) {
    tip.replaceChildren(H("div", { class: "tip-title" }, title));
    for (const r of rows) {
      const row = H("div", { class: "tip-row" });
      const left = H("span", { style: "display:inline-flex;align-items:center;gap:6px" });
      if (r.color) left.appendChild(lineKey(r.color, r.dash, r.shape));
      left.appendChild(document.createTextNode(r.label));
      row.append(left, H("b", {}, r.value));
      tip.appendChild(row);
    }
    tip.hidden = false;
    const w = tip.offsetWidth, h = tip.offsetHeight;
    let x = clientX + 14, y = clientY + 14;
    if (x + w > innerWidth - 8) x = clientX - w - 14;
    if (y + h > innerHeight - 8) y = clientY - h - 14;
    tip.style.left = Math.max(8, x) + "px";
    tip.style.top = Math.max(8, y) + "px";
  }
  const hideTip = () => { tip.hidden = true; };
  window.addEventListener("scroll", hideTip, { passive: true });

  function legend(container, items, onToggle) {
    container.replaceChildren();
    for (const it of items) {
      const el = onToggle ? H("button", { type: "button", class: "item", "aria-pressed": it.hidden ? "false" : "true" })
        : H("span", { class: "item" });
      el.append(lineKey(it.color, it.dash, it.shape), document.createTextNode(it.label));
      if (onToggle) el.addEventListener("click", () => onToggle(it.key));
      container.appendChild(el);
    }
  }

  function table(container, head, rows) {
    const t = H("table");
    const tr = H("tr");
    for (const h of head) tr.appendChild(H("th", {}, h));
    t.appendChild(H("thead")).appendChild(tr);
    const tb = t.appendChild(H("tbody"));
    for (const r of rows) {
      const row = H("tr");
      for (const c of r) row.appendChild(H("td", {}, c));
      tb.appendChild(row);
    }
    container.replaceChildren(t);
  }

  // ---------- line chart with crosshair ----------
  // o: {aria, height, x:{min,max,ticks,format,label}, y:{min,max,log,ticks,format,label,emph,emphLabel},
  //     series:[{key,color,dash,points:[[x,y]...]}], vlines:[{x,label}], markers:[{x,y,color,label,anchor}],
  //     snap(x)->x, title(x)->string, rows(x)->[{label,value,color,dash}], marks:[x...]}
  function lineChart(el, o) {
    const W = widthOf(el), Hh = o.height || 320, m = { l: 48, r: 14, t: 16, b: 46 };
    const pw = W - m.l - m.r, ph = Hh - m.t - m.b;
    const X = (v) => m.l + (v - o.x.min) / (o.x.max - o.x.min) * pw;
    const lg = (v) => Math.log10(Math.min(Math.max(v, o.y.min), o.y.max));
    const Y = o.y.log
      ? (v) => m.t + (Math.log10(o.y.max) - lg(v)) / (Math.log10(o.y.max) - Math.log10(o.y.min)) * ph
      : (v) => m.t + (o.y.max - v) / (o.y.max - o.y.min) * ph;
    const svg = S("svg", { viewBox: `0 0 ${W} ${Hh}`, role: "img", "aria-label": o.aria });
    for (const t of o.y.ticks) {
      S("line", { class: t === o.y.emph ? "axis-strong" : "grid", x1: m.l, x2: W - m.r, y1: Y(t), y2: Y(t) }, svg);
      T(svg, { class: "tick", x: m.l - 6, y: Y(t) + 4, "text-anchor": "end" }, o.y.format(t));
    }
    if (o.y.emph !== undefined && o.y.emphLabel) T(svg, { x: W - m.r - 4, y: Y(o.y.emph) - 5, "text-anchor": "end" }, o.y.emphLabel);
    const xStride = pw < 420 ? 2 : 1;
    o.x.ticks.forEach((t, i) => {
      if (i % xStride === 0) T(svg, { class: "tick", x: X(t), y: Hh - m.b + 16, "text-anchor": "middle" }, o.x.format(t));
    });
    T(svg, { x: m.l + pw / 2, y: Hh - 6, "text-anchor": "middle" }, o.x.label);
    T(svg, { x: m.l, y: m.t - 4 }, o.y.label);
    for (const v of o.vlines || []) {
      S("line", { class: "mark", x1: X(v.x), x2: X(v.x), y1: m.t, y2: m.t + ph }, svg);
      T(svg, { x: X(v.x) + 4, y: m.t + 12 }, v.label);
    }
    for (const xm of o.marks || []) {
      S("line", { x1: X(xm), x2: X(xm), y1: m.t + ph, y2: m.t + ph + 6, style: `stroke:${css("maint")};stroke-width:2` }, svg);
    }
    const clip = `clip${Math.random().toString(36).slice(2, 8)}`;
    S("rect", { x: m.l, y: m.t, width: pw, height: ph }, S("clipPath", { id: clip }, S("defs", {}, svg)));
    const g = S("g", { "clip-path": `url(#${clip})` }, svg);
    for (const se of o.series) {
      if (se.hidden) continue;
      let d = "";
      let pen = false;
      for (const [x, y] of se.points) {
        if (!Number.isFinite(y)) { pen = false; continue; }
        d += `${pen ? "L" : "M"}${X(x).toFixed(1)},${Y(y).toFixed(1)}`;
        pen = true;
      }
      S("path", { d, fill: "none", style: `stroke:${se.color};stroke-width:${se.width || 2};stroke-linejoin:round;stroke-linecap:round;${se.dash ? "stroke-dasharray:6 4" : ""}` }, g);
    }
    // Marker labels that would collide are left out; the tooltip and table still carry them.
    const textWidth = (str) => [...str].reduce((w, ch) => w + (ch.codePointAt(0) > 0x2e80 ? 12 : 6.6), 0);
    const taken = [];
    for (const mk of o.markers || []) {
      if (!Number.isFinite(mk.y) || mk.x < o.x.min || mk.x > o.x.max) continue;
      S("circle", { cx: X(mk.x), cy: Y(mk.y), r: 4.5, style: `fill:${mk.color};stroke:${css("card")};stroke-width:2` }, svg);
      if (!mk.label) continue;
      const x = X(mk.x) + (mk.anchor === "end" ? -8 : 8);
      const w = textWidth(mk.label);
      const x0 = mk.anchor === "end" ? x - w : x, x1 = x0 + w;
      if (x0 < m.l || x1 > W - 2 || taken.some(([a, b]) => x0 < b + 6 && x1 > a - 6)) continue;
      taken.push([x0, x1]);
      T(svg, { x, y: Y(mk.y) + (mk.dy || 16), "text-anchor": mk.anchor || "start" }, mk.label);
    }
    S("line", { class: "axis", x1: m.l, x2: W - m.r, y1: m.t + ph, y2: m.t + ph, style: `stroke:${css("line")}` }, svg);
    // crosshair
    const hair = S("line", { class: "crosshair", y1: m.t, y2: m.t + ph, visibility: "hidden" }, svg);
    const ov = S("rect", { class: "overlay", x: m.l, y: m.t, width: pw, height: ph, tabindex: 0, "aria-label": o.aria }, svg);
    let cur = null;
    const place = (xv, cx, cy) => {
      cur = xv;
      hair.setAttribute("x1", X(xv));
      hair.setAttribute("x2", X(xv));
      hair.setAttribute("visibility", "visible");
      showTip(cx, cy, o.title(xv), o.rows(xv));
    };
    const fromEvent = (ev) => {
      const r = svg.getBoundingClientRect();
      const vx = (ev.clientX - r.left) / r.width * W;
      return o.snap(o.x.min + (vx - m.l) / pw * (o.x.max - o.x.min));
    };
    ov.addEventListener("pointermove", (ev) => place(fromEvent(ev), ev.clientX, ev.clientY));
    ov.addEventListener("pointerleave", () => { hair.setAttribute("visibility", "hidden"); hideTip(); });
    ov.addEventListener("focus", () => {
      const r = svg.getBoundingClientRect();
      const xv = o.snap((o.x.min + o.x.max) / 2);
      place(xv, r.left + r.width / 2, r.top + r.height / 3);
    });
    ov.addEventListener("blur", () => { hair.setAttribute("visibility", "hidden"); hideTip(); });
    ov.addEventListener("keydown", (ev) => {
      if (ev.key !== "ArrowLeft" && ev.key !== "ArrowRight") return;
      ev.preventDefault();
      const step = o.keyStep || (o.x.max - o.x.min) / 40;
      const xv = o.snap(Math.min(o.x.max, Math.max(o.x.min, (cur ?? o.x.min) + (ev.key === "ArrowRight" ? step : -step))));
      const r = svg.getBoundingClientRect();
      place(xv, r.left + (X(xv) / W) * r.width, r.top + r.height / 3);
    });
    el.replaceChildren(svg);
  }

  // ---------- 1. payback calculator ----------
  function calcSeries(betaPct, mc, N, R) {
    const b = betaPct / 100;
    const bounds = [];
    for (let i = 1; i <= R; i++) {
      const k = Math.round((i * N) / (R + 1));
      if (k > 0 && k < N && !bounds.includes(k)) bounds.push(k);
    }
    const s = { zero: [[0, 0]], no: [[0, 0]], ma: [[0, 0]], iZero: [], iNo: [], iMa: [], bounds, at: {} };
    let cNo = 0, cMa = 0, j = 0;
    for (let k = 1; k <= N; k++) {
      j += 1;
      const pNo = 1 + b * k, pMa = 1 + b * j;
      cNo += pNo;
      cMa += pMa;
      s.zero.push([k, k]);
      s.no.push([k, cNo]);
      s.ma.push([k, cMa]);
      s.iZero.push([k, 1]);
      s.iNo.push([k, pNo]);
      s.iMa.push([k, pMa]);
      const before = cMa;
      if (bounds.includes(k)) { cMa += mc; s.ma.push([k, cMa]); j = 0; }
      s.at[k] = { zero: k, no: cNo, maBefore: before, ma: cMa, pNo, pMa, maint: bounds.includes(k) };
    }
    return s;
  }
  function theory(betaPct, mc, N, R) {
    const b = betaPct / 100;
    const net = (r) => (r > 0 ? (b * N * N * r) / (2 * (r + 1)) - r * mc : 0);
    const Q = R > 0 ? (b > 0 ? (2 * (R + 1) * mc) / (b * N * N) : Infinity) : NaN;
    let rStar = 0, best = 0;
    if (b > 0) {
      const cont = N * Math.sqrt(b / (2 * mc)) - 1;
      for (const r of [Math.floor(cont), Math.ceil(cont), 1]) {
        if (r >= 1 && net(r) > best) { best = net(r); rStar = r; }
      }
    }
    return {
      Q, net: net(R), bStar: (400 * mc) / (N * N), nStar: b > 0 ? Math.sqrt((4 * mc) / b) : Infinity,
      rStar, rStarNet: best,
    };
  }
  function initCalc() {
    const root = document.getElementById("calc");
    if (!root) return;
    const $ = (id) => document.getElementById(id);
    const inputs = { beta: $("c-beta"), mc: $("c-mc"), N: $("c-n"), R: $("c-r") };
    const outs = { beta: $("o-beta"), mc: $("o-mc"), N: $("o-n"), R: $("o-r") };
    const state = { view: "cum" };
    const presets = {
      real: { beta: DS.real.beta * 100, mc: DS.real.mc, N: Math.round(DS.real.N0), R: Math.round(DS.real.R) },
      real0: { beta: 0, mc: DS.real.mc, N: Math.round(DS.real.N0), R: Math.round(DS.real.R) },
      strong: { beta: DS.strong.beta * 100, mc: DS.strong.mc, N: Math.round(DS.strong.N0), R: Math.round(DS.strong.R) },
      weak: { beta: DS.weak.beta * 100, mc: DS.weak.mc, N: Math.round(DS.weak.N0), R: Math.round(DS.weak.R) },
    };
    const presetButtons = root.querySelectorAll("[data-preset]");
    function setPreset(key) {
      const p = presets[key];
      inputs.beta.value = p.beta.toFixed(2);
      inputs.mc.value = p.mc.toFixed(1);
      inputs.N.value = p.N;
      inputs.R.value = p.R;
      presetButtons.forEach((b) => b.setAttribute("aria-pressed", b.dataset.preset === key ? "true" : "false"));
      render();
    }
    function read() {
      return { beta: +inputs.beta.value, mc: +inputs.mc.value, N: +inputs.N.value, R: +inputs.R.value };
    }
    function render() {
      const v = read();
      outs.beta.textContent = v.beta.toFixed(2);
      outs.mc.textContent = v.mc.toFixed(1);
      outs.N.textContent = v.N;
      outs.R.textContent = v.R;
      const th = theory(v.beta, v.mc, v.N, v.R);
      $("t-q").textContent = v.R > 0 ? fmt(th.Q, 2) : "–";
      const verdict = $("t-verdict");
      verdict.className = "t-note " + (v.R === 0 ? "" : th.Q < 1 ? "verdict-yes" : "verdict-no");
      verdict.textContent = v.R === 0 ? L.verdict.na : th.Q < 1 ? L.verdict.yes : L.verdict.no;
      $("t-net").textContent = (th.net >= 0 ? "+" : "") + th.net.toFixed(2);
      $("t-bstar").textContent = th.bStar.toFixed(2) + " " + L.units.pctItem;
      $("t-rstar").textContent = String(th.rStar);
      $("t-nstar").textContent = (th.nStar === Infinity ? L.nstar_inf : tpl(L.nstar, { n: th.nStar.toFixed(0) }))
        + (th.rStar > 0 ? " · " + tpl(L.rstar_note, { net: "+" + th.rStarNet.toFixed(2) }) : "");
      const s = calcSeries(v.beta, v.mc, v.N, v.R);
      const maintLabel = tpl(L.series.maint, { R: v.R });
      const items = [
        { key: "no", label: L.series.nomaint, color: css("nomaint"), dash: true },
        { key: "ma", label: maintLabel, color: css("maint") },
        { key: "zero", label: L.series.zero, color: css("zero"), width: 1.5 },
      ];
      legend(document.getElementById("calc-legend"), items);
      const cum = state.view === "cum";
      const series = cum
        ? [{ ...items[2], points: s.zero }, { ...items[0], points: s.no }, { ...items[1], points: s.ma }]
        : [{ ...items[2], points: s.iZero }, { ...items[0], points: s.iNo }, { ...items[1], points: s.iMa }];
      const ymax = cum ? Math.max(s.at[v.N].no, s.at[v.N].ma, v.N) * 1.04 : (1 + (v.beta / 100) * v.N) * 1.06;
      const ymin = cum ? 0 : Math.max(0, 1 - (ymax - 1) * 0.3);
      lineChart(document.getElementById("calc-chart"), {
        aria: cum ? L.axis.cum : L.axis.item,
        x: { min: 0, max: v.N, ticks: niceTicks(0, v.N, 8), format: String, label: L.axis.k },
        y: { min: ymin, max: ymax, ticks: niceTicks(ymin, ymax, 5), format: (t) => String(+t.toFixed(2)), label: cum ? L.axis.cum : L.axis.item },
        series,
        marks: s.bounds,
        snap: (x) => Math.min(v.N, Math.max(1, Math.round(x))),
        keyStep: 1,
        title: (k) => tpl(L.tip.k_at, { k }) + (s.at[k] && s.at[k].maint ? " · " + L.tip.maint_at : ""),
        rows: (k) => {
          const a = s.at[k];
          return cum
            ? [{ label: L.series.nomaint, value: a.no.toFixed(2), color: css("nomaint"), dash: true },
              { label: maintLabel, value: a.ma.toFixed(2), color: css("maint") },
              { label: L.series.zero, value: a.zero.toFixed(2), color: css("zero") }]
            : [{ label: L.series.nomaint, value: a.pNo.toFixed(3), color: css("nomaint"), dash: true },
              { label: maintLabel, value: a.pMa.toFixed(3), color: css("maint") },
              { label: L.series.zero, value: "1.000", color: css("zero") }];
        },
      });
      const stride = Math.max(1, Math.ceil(v.N / 20));
      const rows = [];
      for (let k = stride; k <= v.N; k += stride) {
        const a = s.at[k];
        rows.push(cum ? [k, a.no.toFixed(2), a.ma.toFixed(2), a.zero.toFixed(2)] : [k, a.pNo.toFixed(3), a.pMa.toFixed(3), "1.000"]);
      }
      table(document.getElementById("calc-table"), [L.table.k, L.series.nomaint, maintLabel, L.series.zero], rows);
    }
    Object.values(inputs).forEach((i) => i.addEventListener("input", () => {
      presetButtons.forEach((b) => b.setAttribute("aria-pressed", "false"));
      render();
    }));
    presetButtons.forEach((b) => b.addEventListener("click", () => setPreset(b.dataset.preset)));
    root.querySelectorAll("[data-view]").forEach((b) => b.addEventListener("click", () => {
      state.view = b.dataset.view;
      root.querySelectorAll("[data-view]").forEach((x) => x.setAttribute("aria-pressed", x === b ? "true" : "false"));
      render();
    }));
    renderers.push(render);
    setPreset("real");
  }

  // ---------- 2. payback horizon Q(T) ----------
  const qOfT = (d, beta, t) => (beta > 0 ? (2 * (d.r * t + 1) * d.mc) / (beta * (d.v * t) ** 2) : Infinity);
  function tStar(d, beta) {
    if (beta <= 0) return Infinity;
    const a = beta * d.v * d.v, b = -2 * d.r * d.mc, c = -2 * d.mc;
    return (-b + Math.sqrt(b * b - 4 * a * c)) / (2 * a);
  }
  function initQ() {
    const root = document.getElementById("qviz");
    if (!root) return;
    const TMAX = 40;
    const state = { hidden: {}, realBeta: "point" };
    const colors = { strong: css("ds-strong"), weak: css("ds-weak"), real: css("ds-real") };
    const betaOf = (k) => (k === "real" && state.realBeta === "hi" ? DS.real.beta_hi : DS[k].beta);
    function render() {
      const keys = ["strong", "weak", "real"];
      const items = keys.map((k) => ({ key: k, label: L.series[k], color: colors[k], dash: k === "real", hidden: !!state.hidden[k] }));
      legend(document.getElementById("q-legend"), items, (k) => { state.hidden[k] = !state.hidden[k]; render(); });
      const series = items.map((it) => {
        const pts = [];
        for (let t = 1; t <= TMAX + 1e-9; t += 0.25) pts.push([t, qOfT(DS[it.key], betaOf(it.key), t)]);
        return { ...it, points: pts };
      });
      const markers = [];
      for (const it of items) {
        if (it.hidden) continue;
        const ts = tStar(DS[it.key], betaOf(it.key));
        if (ts <= TMAX) {
          markers.push({ x: ts, y: 1, color: it.color, label: tpl(L.tstar, { t: ts.toFixed(1) }), dy: 18,
            anchor: ts > TMAX * 0.8 ? "end" : "start" });
        }
      }
      lineChart(document.getElementById("q-chart"), {
        aria: L.axis.Q,
        height: 340,
        x: { min: 1, max: TMAX, ticks: [1, 4, 8, 12, 16, 20, 24, 28, 32, 36, 40], format: String, label: L.axis.T },
        y: { min: 0.1, max: 20, log: true, ticks: [0.1, 0.2, 0.5, 1, 2, 5, 10, 20], format: String, label: L.axis.Q, emph: 1, emphLabel: L.ref.breakeven },
        series,
        vlines: [{ x: 8, label: L.ref.horizon }],
        markers,
        snap: (x) => Math.min(TMAX, Math.max(1, Math.round(x * 2) / 2)),
        keyStep: 0.5,
        title: (t) => tpl(L.tip.T, { T: t }),
        rows: (t) => items.filter((it) => !it.hidden).map((it) => {
          const q = qOfT(DS[it.key], betaOf(it.key), t);
          return { label: it.label, value: `${fmt(q, 2)} · ${q < 1 ? L.tip.paid : L.tip.unpaid}`, color: it.color, dash: it.dash };
        }),
      });
      table(document.getElementById("q-table"), [L.table.dataset, L.table.tstar, L.table.q8], keys.map((k) => {
        const ts = tStar(DS[k], betaOf(k));
        return [L.series[k], ts === Infinity ? L.units.inf : ts.toFixed(1), fmt(qOfT(DS[k], betaOf(k), 8), 2)];
      }));
    }
    root.querySelectorAll("[data-beta]").forEach((b) => b.addEventListener("click", () => {
      state.realBeta = b.dataset.beta;
      root.querySelectorAll("[data-beta]").forEach((x) => x.setAttribute("aria-pressed", x === b ? "true" : "false"));
      render();
    }));
    renderers.push(render);
    render();
  }

  // ---------- 3. on-the-spot rule, every maintenance run ----------
  function initOnline() {
    const root = document.getElementById("online");
    if (!root) return;
    const slider = document.getElementById("on-beta");
    const out = document.getElementById("on-o-beta");
    const state = { k: "type" };
    const shapes = { maint_tests: "circle", maint_refactor: "square", maint_security: "diamond", maint_knowledge: "triangle" };
    slider.value = (DS.real.beta * 100).toFixed(2);
    const presetButtons = root.querySelectorAll("[data-beta]");
    function syncPresets() {
      presetButtons.forEach((b) => b.setAttribute("aria-pressed", Math.abs(+b.dataset.beta - +slider.value) < 0.005 ? "true" : "false"));
    }
    function evaluate() {
      const b = +slider.value / 100;
      return DATA.events.map((e) => {
        const k = state.k === "type" ? e.k_type : e.k_single;
        const score = b * k * e.n_rem;
        return { ...e, k, score, worth: score > e.mc };
      });
    }
    function drawShape(g, shape, cx, cy, color) {
      const st = `fill:${color};stroke:${css("card")};stroke-width:2`;
      if (shape === "square") return S("rect", { class: "pt", x: cx - 5, y: cy - 5, width: 10, height: 10, rx: 1.5, style: st }, g);
      if (shape === "diamond") return S("path", { class: "pt", d: `M${cx},${cy - 6}L${cx + 6},${cy}L${cx},${cy + 6}L${cx - 6},${cy}Z`, style: st }, g);
      if (shape === "triangle") return S("path", { class: "pt", d: `M${cx},${cy - 6}L${cx + 6},${cy + 5}L${cx - 6},${cy + 5}Z`, style: st }, g);
      return S("circle", { class: "pt", cx, cy, r: 5.5, style: st }, g);
    }
    function render() {
      out.textContent = (+slider.value).toFixed(2);
      syncPresets();
      const ev = evaluate();
      const worth = ev.filter((e) => e.worth).length;
      document.getElementById("on-count").textContent = `${worth} / ${ev.length}`;
      const present = [...new Set(ev.map((e) => e.type))];
      legend(document.getElementById("online-legend"), [
        ...present.map((t) => ({ label: L.types[t] || t, color: css("maint"), shape: shapes[t] || "circle" })),
        { label: L.ref.diag, color: css("muted"), dash: true },
      ]);
      // scatter
      const chartEl = document.getElementById("online-chart");
      const W = widthOf(chartEl), Hh = Math.min(360, Math.max(280, W * 0.55)), m = { l: 48, r: 14, t: 18, b: 46 };
      const pw = W - m.l - m.r, ph = Hh - m.t - m.b;
      const maxv = Math.max(4, ...ev.map((e) => e.score), ...ev.map((e) => e.mc)) * 1.08;
      const X = (v) => m.l + (v / maxv) * pw;
      const Y = (v) => m.t + ph - (v / maxv) * ph;
      const svg = S("svg", { viewBox: `0 0 ${W} ${Hh}`, role: "img", "aria-label": L.axis.benefit });
      S("path", { d: `M${X(0)},${Y(0)}L${X(maxv)},${Y(maxv)}L${X(0)},${Y(maxv)}Z`, style: `fill:${css("wash")}` }, svg);
      const ticks = niceTicks(0, maxv, 5);
      for (const t of ticks) {
        S("line", { class: "grid", x1: m.l, x2: W - m.r, y1: Y(t), y2: Y(t) }, svg);
        T(svg, { class: "tick", x: m.l - 6, y: Y(t) + 4, "text-anchor": "end" }, String(t));
        T(svg, { class: "tick", x: X(t), y: Hh - m.b + 16, "text-anchor": "middle" }, String(t));
      }
      S("line", { x1: m.l, x2: W - m.r, y1: m.t + ph, y2: m.t + ph, style: `stroke:${css("line")}` }, svg);
      S("line", { x1: X(0), y1: Y(0), x2: X(maxv), y2: Y(maxv), style: `stroke:${css("muted")};stroke-width:1.2;stroke-dasharray:5 4` }, svg);
      T(svg, { x: X(maxv * 0.06), y: Y(maxv * 0.93) }, L.ref.above);
      T(svg, { x: X(maxv) - 4, y: Y(maxv) + 26, "text-anchor": "end" }, L.ref.diag);
      T(svg, { x: m.l + pw / 2, y: Hh - 6, "text-anchor": "middle" }, L.axis.cost);
      T(svg, { x: m.l, y: m.t - 5 }, L.axis.benefit);
      // jitter identical positions slightly so every point stays reachable
      const seen = {};
      ev.forEach((e, i) => {
        const key = `${e.mc.toFixed(2)}|${e.score.toFixed(2)}`;
        const n = (seen[key] = (seen[key] || 0) + 1) - 1;
        const cx = X(e.mc) + n * 7, cy = Y(e.score) - n * 7;
        const g = S("g", { class: "pt-g" }, svg);
        drawShape(g, shapes[e.type] || "circle", cx, cy, css("maint"));
        const hit = S("circle", { class: "hit", cx, cy, r: 12, tabindex: 0, "aria-label": `${tpl(L.tip.event, e)} ${L.types[e.type] || e.type}` }, g);
        const rows = () => [
          { label: L.tip.benefit, value: e.score.toFixed(2) },
          { label: L.tip.cost, value: e.mc.toFixed(2) },
          { label: L.tip.k, value: String(e.k) },
          { label: L.tip.n_rem, value: String(e.n_rem) },
          { label: e.worth ? L.tip.worth : L.tip.not_worth, value: e.worth ? "✓" : "✗" },
        ];
        const title = () => `${tpl(L.tip.event, e)} · ${L.types[e.type] || e.type}`;
        hit.addEventListener("pointermove", (p) => showTip(p.clientX, p.clientY, title(), rows()));
        hit.addEventListener("pointerleave", hideTip);
        hit.addEventListener("focus", () => {
          const r = hit.getBoundingClientRect();
          showTip(r.right, r.top, title(), rows());
        });
        hit.addEventListener("blur", hideTip);
      });
      chartEl.replaceChildren(svg);
      const tb = document.getElementById("online-tbody");
      tb.replaceChildren(...ev.map((e) => {
        const tr = H("tr");
        for (const c of [e.rep, e.week, L.types[e.type] || e.type, e.k, e.n_rem, e.score.toFixed(2), e.mc.toFixed(2), e.worth ? L.yes : L.no]) {
          tr.appendChild(H("td", {}, String(c)));
        }
        return tr;
      }));
    }
    slider.addEventListener("input", render);
    presetButtons.forEach((b) => b.addEventListener("click", () => { slider.value = (+b.dataset.beta).toFixed(2); render(); }));
    root.querySelectorAll("[data-k]").forEach((b) => b.addEventListener("click", () => {
      state.k = b.dataset.k;
      root.querySelectorAll("[data-k]").forEach((x) => x.setAttribute("aria-pressed", x === b ? "true" : "false"));
      render();
    }));
    renderers.push(render);
    render();
  }

  initCalc();
  initQ();
  initOnline();
})();
