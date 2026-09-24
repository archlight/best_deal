/* Small dependency-free SVG charts: multi-series line, horizontal bar, heatmap. */
(function () {
  const NS = "http://www.w3.org/2000/svg";
  const tooltip = () => document.getElementById("tooltip");

  function el(name, attrs = {}, parent) {
    const node = document.createElementNS(NS, name);
    for (const [k, v] of Object.entries(attrs)) node.setAttribute(k, v);
    if (parent) parent.appendChild(node);
    return node;
  }

  function esc(s) {
    return String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  }

  function showTip(evt, html) {
    const tip = tooltip();
    tip.innerHTML = html;
    tip.hidden = false;
    const pad = 14;
    const { innerWidth: w, innerHeight: h } = window;
    const r = tip.getBoundingClientRect();
    let x = evt.clientX + pad, y = evt.clientY + pad;
    if (x + r.width > w - 8) x = evt.clientX - r.width - pad;
    if (y + r.height > h - 8) y = evt.clientY - r.height - pad;
    tip.style.left = Math.max(8, x) + "px";
    tip.style.top = Math.max(8, y) + "px";
  }
  const hideTip = () => { tooltip().hidden = true; };

  function niceTicks(min, max, count = 4) {
    if (min === max) { min -= 1; max += 1; }
    const raw = (max - min) / count;
    const mag = Math.pow(10, Math.floor(Math.log10(raw)));
    const step = [1, 2, 2.5, 5, 10].map((m) => m * mag).find((s) => s >= raw);
    const lo = Math.floor(min / step) * step, hi = Math.ceil(max / step) * step;
    const ticks = [];
    for (let v = lo; v <= hi + step / 2; v += step) ticks.push(+v.toFixed(10));
    return ticks;
  }

  function legend(container, series) {
    if (series.length < 2) return;
    const div = document.createElement("div");
    div.className = "legend";
    div.innerHTML = series.map((s) => `<span><span class="dot" style="background:${s.color}"></span>${esc(s.name)}</span>`).join("");
    container.appendChild(div);
  }

  function tableView(container, headers, rows) {
    const d = document.createElement("details");
    d.className = "table-view";
    d.innerHTML = `<summary>Show as table</summary><div class="table-scroll"><table><thead><tr>${headers
      .map((h, i) => `<th class="${i ? "num" : ""}">${esc(h)}</th>`).join("")}</tr></thead><tbody>${rows
      .map((r) => `<tr>${r.map((c, i) => `<td class="${i ? "num" : ""}">${esc(c ?? "–")}</td>`).join("")}</tr>`).join("")}</tbody></table></div>`;
    container.appendChild(d);
  }

  /**
   * Line chart with crosshair tooltip.
   * opts: { categories: [label], series: [{name, color, values: [number|null]}], yFormat, xLabelEvery }
   */
  function lineChart(container, opts) {
    container.innerHTML = "";
    const { categories, series, yFormat = (v) => v.toFixed(2) } = opts;
    legend(container, series);
    // Size to the container so text renders at its real pixel size.
    const W = Math.max(300, container.clientWidth || 640), H = 260, m = { t: 12, r: 16, b: 28, l: 44 };
    const all = series.flatMap((s) => s.values).filter((v) => v != null);
    if (!all.length) { container.insertAdjacentHTML("beforeend", '<p class="muted small">No data yet.</p>'); return; }
    const ticks = niceTicks(Math.min(...all), Math.max(...all));
    const y0 = ticks[0], y1 = ticks[ticks.length - 1];
    const x = (i) => m.l + (categories.length === 1 ? 0 : (i / (categories.length - 1)) * (W - m.l - m.r));
    const y = (v) => H - m.b - ((v - y0) / (y1 - y0 || 1)) * (H - m.t - m.b);
    const svg = el("svg", { viewBox: `0 0 ${W} ${H}`, role: "img", "aria-label": opts.ariaLabel || "Line chart" }, container);

    ticks.forEach((t) => {
      el("line", { x1: m.l, x2: W - m.r, y1: y(t), y2: y(t), class: t === y0 ? "baseline" : "gridline" }, svg);
      el("text", { x: m.l - 6, y: y(t) + 4, "text-anchor": "end" }, svg).textContent = yFormat(t);
    });
    // Keep x labels ~70px apart so they never collide on narrow screens.
    const maxLabels = Math.max(2, Math.floor((W - m.l - m.r) / 70));
    const every = Math.max(opts.xLabelEvery || 1, Math.ceil(categories.length / maxLabels));
    categories.forEach((c, i) => {
      if (i % every === 0) el("text", { x: x(i), y: H - 8, "text-anchor": "middle" }, svg).textContent = c;
    });

    series.forEach((s) => {
      let d = "", pen = false;
      s.values.forEach((v, i) => {
        if (v == null) { pen = false; return; }
        d += `${pen ? "L" : "M"}${x(i).toFixed(1)},${y(v).toFixed(1)}`;
        pen = true;
      });
      el("path", { d, class: "series-line", style: `stroke:${s.color}` }, svg);
      // Lone points (no neighbours) would be invisible as a path; mark them.
      s.values.forEach((v, i) => {
        if (v != null && s.values[i - 1] == null && s.values[i + 1] == null)
          el("circle", { cx: x(i), cy: y(v), r: 4, style: `fill:${s.color}` }, svg);
      });
    });

    const cross = el("line", { y1: m.t, y2: H - m.b, class: "crosshair", visibility: "hidden" }, svg);
    const dots = series.map((s) => el("circle", { r: 5, style: `fill:${s.color};stroke:var(--surface);stroke-width:2`, visibility: "hidden" }, svg));
    const hit = el("rect", { x: m.l, y: m.t, width: W - m.l - m.r, height: H - m.t - m.b, fill: "transparent" }, svg);
    hit.addEventListener("mousemove", (evt) => {
      const pt = svg.createSVGPoint(); pt.x = evt.clientX; pt.y = evt.clientY;
      const p = pt.matrixTransform(svg.getScreenCTM().inverse());
      const i = Math.max(0, Math.min(categories.length - 1, Math.round(((p.x - m.l) / (W - m.l - m.r)) * (categories.length - 1))));
      cross.setAttribute("x1", x(i)); cross.setAttribute("x2", x(i)); cross.setAttribute("visibility", "visible");
      series.forEach((s, k) => {
        const v = s.values[i];
        if (v == null) { dots[k].setAttribute("visibility", "hidden"); return; }
        dots[k].setAttribute("cx", x(i)); dots[k].setAttribute("cy", y(v)); dots[k].setAttribute("visibility", "visible");
      });
      const rows = series
        .map((s) => ({ s, v: s.values[i] }))
        .filter((r) => r.v != null)
        .sort((a, b) => a.v - b.v)
        .map((r) => `<div class="t-row"><span><span class="dot" style="background:${r.s.color}"></span>${esc(r.s.name)}</span><span>${yFormat(r.v)}</span></div>`)
        .join("");
      showTip(evt, `<div class="t-head">${esc(categories[i])}</div>${rows || '<span class="muted">No data</span>'}`);
    });
    hit.addEventListener("mouseleave", () => {
      cross.setAttribute("visibility", "hidden"); dots.forEach((d) => d.setAttribute("visibility", "hidden")); hideTip();
    });

    tableView(container, ["", ...series.map((s) => s.name)], categories.map((c, i) => [c, ...series.map((s) => (s.values[i] == null ? null : yFormat(s.values[i])))]));
  }

  /** Horizontal bars. items: [{label, value, color, detail}] */
  function barChart(container, items, opts = {}) {
    container.innerHTML = "";
    if (!items.length) { container.innerHTML = '<p class="muted small">No data yet.</p>'; return; }
    const fmt = opts.format || ((v) => v);
    const W = Math.max(300, container.clientWidth || 640), rowH = 34, barH = 18, labelW = 120, valueW = 56;
    const H = items.length * rowH + 4;
    const max = opts.max ?? Math.max(...items.map((d) => d.value), 0.0001);
    const svg = el("svg", { viewBox: `0 0 ${W} ${H}`, role: "img", "aria-label": opts.ariaLabel || "Bar chart" }, container);
    const span = W - labelW - valueW;
    items.forEach((d, i) => {
      const yTop = i * rowH + (rowH - barH) / 2;
      const g = el("g", {}, svg);
      el("text", { x: 0, y: yTop + barH / 2 + 4, class: "label-ink" }, g).textContent = d.label;
      const w = Math.max((d.value / max) * span, d.value > 0 ? 4 : 0);
      // Square at the baseline, 4px rounded data end.
      const r = Math.min(4, w / 2);
      el("path", {
        d: `M${labelW},${yTop}h${w - r}a${r},${r} 0 0 1 ${r},${r}v${barH - 2 * r}a${r},${r} 0 0 1 -${r},${r}h-${w - r}z`,
        style: `fill:${d.color}`,
      }, g);
      el("text", { x: labelW + w + 6, y: yTop + barH / 2 + 4, class: "value-ink" }, g).textContent = fmt(d.value);
      const hit = el("rect", { x: 0, y: i * rowH, width: W, height: rowH, fill: "transparent" }, g);
      hit.addEventListener("mousemove", (evt) => showTip(evt, `<div class="t-head">${esc(d.label)}</div>${d.detail || esc(fmt(d.value))}`));
      hit.addEventListener("mouseleave", hideTip);
    });
    el("line", { x1: labelW, x2: labelW, y1: 0, y2: H, class: "baseline" }, svg);
  }

  /** Weekday x hour heatmap on the sequential ramp. cells: [{weekday, day, hour, value, n}] */
  function heatmap(container, cells, opts = {}) {
    container.innerHTML = "";
    if (!cells.length) { container.innerHTML = '<p class="muted small">No data yet.</p>'; return; }
    const fmt = opts.format || ((v) => v.toFixed(2));
    const days = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];
    const W = Math.max(560, container.clientWidth || 760), cell = 26, gap = 2, left = 40, top = 18;
    const H = top + 7 * (cell + gap) + 30;
    const vals = cells.map((c) => c.value);
    const lo = Math.min(...vals), hi = Math.max(...vals);
    const steps = 7;
    const bucket = (v) => (hi === lo ? 3 : Math.min(steps - 1, Math.floor(((v - lo) / (hi - lo)) * steps)));
    const cw = (W - left) / 24 - gap;
    const svg = el("svg", { viewBox: `0 0 ${W} ${H}`, role: "img", "aria-label": opts.ariaLabel || "Heatmap" }, container);
    for (let h = 0; h < 24; h += 3) el("text", { x: left + h * (cw + gap) + cw / 2, y: 11, "text-anchor": "middle" }, svg).textContent = `${String(h).padStart(2, "0")}h`;
    days.forEach((d, i) => el("text", { x: left - 8, y: top + i * (cell + gap) + cell / 2 + 4, "text-anchor": "end" }, svg).textContent = d);
    // Empty grid so missing cells read as "no data" rather than "cheap".
    for (let wd = 0; wd < 7; wd++)
      for (let h = 0; h < 24; h++)
        el("rect", { x: left + h * (cw + gap), y: top + wd * (cell + gap), width: cw, height: cell, rx: 3, style: "fill:var(--surface-2)" }, svg);
    cells.forEach((c) => {
      const r = el("rect", {
        x: left + c.hour * (cw + gap), y: top + c.weekday * (cell + gap), width: cw, height: cell, rx: 3,
        style: `fill:var(--seq-${bucket(c.value)})`,
      }, svg);
      r.addEventListener("mousemove", (evt) => showTip(evt, `<div class="t-head">${c.day} ${String(c.hour).padStart(2, "0")}:00</div>${esc(fmt(c.value))} per km · ${c.n} search${c.n === 1 ? "" : "es"}`));
      r.addEventListener("mouseleave", hideTip);
    });
    // Ramp legend
    const ly = top + 7 * (cell + gap) + 10;
    el("text", { x: left, y: ly + 11 }, svg).textContent = fmt(lo);
    for (let i = 0; i < steps; i++) el("rect", { x: left + 44 + i * 22, y: ly, width: 20, height: 12, rx: 2, style: `fill:var(--seq-${i})` }, svg);
    el("text", { x: left + 44 + steps * 22 + 6, y: ly + 11 }, svg).textContent = fmt(hi);
  }

  window.Charts = { lineChart, barChart, heatmap, esc };
})();
