/* SPDX-License-Identifier: GPL-3.0-or-later
 * Copyright (C) <YEAR> <AUTHOR>
 *
 * Hand-written SVG charts (no libraries).
 */
import { h, s } from "./dom.js";

function niceMax(v) {
  if (v <= 0) return 1;
  const exp = Math.pow(10, Math.floor(Math.log10(v)));
  for (const m of [1, 2, 2.5, 5, 10]) if (m * exp >= v) return m * exp;
  return 10 * exp;
}

/**
 * RTT line chart. points: [{seq, rtt|null}] (null = lost).
 * Returns a <figure> with an accessible description.
 */
export function rttChart(points, { label = "Round-trip time per packet", unit = "ms" } = {}) {
  const W = 640;
  const H = 200;
  const pad = { l: 48, r: 12, t: 10, b: 28 };
  const iw = W - pad.l - pad.r;
  const ih = H - pad.t - pad.b;
  const values = points.filter((p) => p.rtt !== null && p.rtt !== undefined).map((p) => p.rtt);
  const max = niceMax(values.length ? Math.max(...values) * 1.1 : 1);
  const n = Math.max(points.length, 2);
  const seqs = points.map((p) => p.seq);
  const minSeq = seqs.length ? Math.min(...seqs) : 1;
  const maxSeq = seqs.length ? Math.max(...seqs) : 2;
  const span = Math.max(maxSeq - minSeq, n - 1, 1);
  const x = (seq) => pad.l + ((seq - minSeq) / span) * iw;
  const y = (v) => pad.t + ih - (v / max) * ih;

  const svg = s("svg", { viewBox: `0 0 ${W} ${H}`, role: "img", "aria-label": label, preserveAspectRatio: "xMidYMid meet" });
  const grid = s("g", { class: "grid" });
  const axis = s("g", { class: "axis" });
  const step = max / 4;
  const digits = step >= 10 ? 0 : step >= 1 ? 1 : Math.min(4, Math.ceil(-Math.log10(step)) + 1);
  for (let i = 0; i <= 4; i++) {
    const v = step * i;
    const yy = y(v);
    grid.appendChild(s("line", { x1: pad.l, x2: W - pad.r, y1: yy, y2: yy }));
    axis.appendChild(s("text", { x: pad.l - 6, y: yy + 4, "text-anchor": "end" }, `${+v.toFixed(digits)}`));
  }
  axis.appendChild(s("text", { x: 4, y: pad.t + 10 }, unit));
  const ticks = Math.min(points.length, 10);
  for (let i = 0; i < ticks; i++) {
    const seq = Math.round(minSeq + (span * i) / Math.max(ticks - 1, 1));
    axis.appendChild(s("text", { x: x(seq), y: H - 8, "text-anchor": "middle" }, String(seq)));
  }
  svg.appendChild(grid);

  // Lost packets: a red band plus a vertical tick (so it isn't colour-only, the legend + table say "lost").
  for (const p of points) {
    if (p.rtt === null || p.rtt === undefined) {
      const xx = x(p.seq);
      svg.appendChild(s("rect", { class: "lost-band", x: xx - 4, y: pad.t, width: 8, height: ih }));
      svg.appendChild(s("line", { class: "lost", x1: xx, x2: xx, y1: pad.t, y2: pad.t + ih }));
      svg.appendChild(s("text", { class: "axis-lost", x: xx, y: pad.t + 10, "text-anchor": "middle" }, "✕"));
    }
  }
  // The series is broken at lost packets.
  let d = "";
  let pen = false;
  for (const p of points) {
    if (p.rtt === null || p.rtt === undefined) {
      pen = false;
      continue;
    }
    d += `${pen ? "L" : "M"}${x(p.seq).toFixed(1)},${y(p.rtt).toFixed(1)}`;
    pen = true;
  }
  if (d) svg.appendChild(s("path", { class: "series", d }));
  for (const p of points) {
    if (p.rtt !== null && p.rtt !== undefined && points.length <= 120) {
      svg.appendChild(s("circle", { class: "point", cx: x(p.seq), cy: y(p.rtt), r: 2.5 }));
    }
  }
  svg.appendChild(axis);

  const lost = points.length - values.length;
  return h(
    "figure",
    { class: "chart" },
    svg,
    h(
      "figcaption",
      { class: "chart-legend" },
      h("span", {}, h("span", { class: "swatch", "aria-hidden": "true" }), `RTT (${unit}), x = packet number`),
      lost ? h("span", {}, h("span", { class: "swatch lost", "aria-hidden": "true" }), `✕ lost packet (${lost})`) : null,
    ),
  );
}

/**
 * Stacked horizontal bar. parts: [{label, value}] in ms.
 * The legend lists every value as text.
 */
export function stackedBar(parts, { label = "Timing breakdown", unit = "ms" } = {}) {
  const total = parts.reduce((a, p) => a + Math.max(0, p.value || 0), 0) || 1;
  const bar = h("div", { class: "stacked-bar", role: "img", "aria-label": `${label}: ${parts.map((p) => `${p.label} ${p.value.toFixed(1)} ${unit}`).join(", ")}` });
  parts.forEach((p, i) => {
    const seg = h("span", { class: `bar-${(i % 5) + 1}`, title: `${p.label}: ${p.value.toFixed(1)} ${unit}` });
    seg.style.flexGrow = String(Math.max(0, p.value) / total);
    seg.style.flexBasis = "0";
    bar.appendChild(seg);
  });
  const legend = h(
    "ul",
    { class: "bar-legend" },
    parts.map((p, i) => h("li", {}, h("span", { class: `swatch bar-${(i % 5) + 1}`, "aria-hidden": "true" }), h("span", {}, `${p.label}: ${p.value.toFixed(1)} ${unit}`))),
  );
  return h("figure", { class: "chart" }, bar, legend);
}

/** A small inline meter (e.g. packet loss %), always with a text value next to it. */
export function meter(percent) {
  const m = h("span", { class: "meter", "aria-hidden": "true" }, h("span"));
  m.firstChild.style.width = `${Math.max(0, Math.min(100, percent))}%`;
  return m;
}
