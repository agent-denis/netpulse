/* SPDX-License-Identifier: GPL-3.0-or-later
 * Copyright (C) 2026 Denis
 */
import { meter } from "../chart.js";
import { formatMs, h } from "../dom.js";
import { level, stats, statusText, summaryLine, table } from "../render.js";
import { FAMILY } from "./ping.js";

function loss(r) {
  if (r.loss_pct === null || r.loss_pct === undefined) return "–";
  const lvl = r.loss_pct === 0 ? "ok" : r.loss_pct >= 100 ? "err" : "warn";
  return h("span", {}, meter(r.loss_pct), statusText(lvl, `${+Number(r.loss_pct).toFixed(1)} %`));
}

export default {
  fields: [
    { name: "host", label: "Host or IP address", type: "text", required: true, placeholder: "e.g. fedoraproject.org", width: "span-2", mono: true },
    { name: "cycles", label: "Cycles", type: "number", min: 1, max: 100, step: 1, default: 10, help: "One cycle per second" },
    { name: "max_hops", label: "Max hops", type: "number", min: 1, max: 64, step: 1, default: 30 },
    {
      name: "mode",
      label: "Probe type",
      type: "segmented",
      options: [
        { value: "udp", label: "UDP" },
        { value: "icmp", label: "ICMP" },
        { value: "tcp", label: "TCP 443" },
      ],
      default: "udp",
    },
    FAMILY,
    { name: "resolve", label: "Resolve hostnames", type: "checkbox", default: true },
  ],
  verdict: (s) => s.message || "",
  render(s) {
    const nodes = [];
    if (s.progress !== undefined) {
      const bar = h("progress", { max: "100", value: String(Math.round(s.progress * 100)), "aria-label": "mtr progress" });
      return h("div", {}, h("p", { class: "muted" }, s.message), bar);
    }
    if (s.message) nodes.push(summaryLine(level(s.status), s.message));
    nodes.push(
      stats([
        { label: "Hops", value: String(s.hop_count ?? 0) },
        { label: "Cycles", value: String(s.cycles ?? "–") },
        { label: "Loss at destination", value: s.final_loss_pct === null || s.final_loss_pct === undefined ? "–" : `${s.final_loss_pct} %`, level: s.final_loss_pct === 0 ? "ok" : s.final_loss_pct >= 100 ? "err" : s.final_loss_pct ? "warn" : "neutral" },
      ]),
    );
    nodes.push(
      table(
        [
          { key: "hop", label: "Hop", num: true },
          { key: "host", label: "Host", mono: true, render: (r) => r.host || "???" },
          { key: "loss", label: "Loss", render: loss },
          { key: "sent", label: "Sent", num: true },
          { key: "last", label: "Last", num: true, render: (r) => (r.loss_pct >= 100 ? "–" : formatMs(r.last, 1)) },
          { key: "avg", label: "Avg", num: true, render: (r) => (r.loss_pct >= 100 ? "–" : formatMs(r.avg, 1)) },
          { key: "best", label: "Best", num: true, render: (r) => (r.loss_pct >= 100 ? "–" : formatMs(r.best, 1)) },
          { key: "worst", label: "Worst", num: true, render: (r) => (r.loss_pct >= 100 ? "–" : formatMs(r.worst, 1)) },
          { key: "stdev", label: "StDev", num: true, render: (r) => (r.loss_pct >= 100 ? "–" : formatMs(r.stdev, 1)) },
        ],
        s.hops || [],
        { caption: "Hops" },
      ),
    );
    return h("div", {}, nodes);
  },
};
