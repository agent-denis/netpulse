/* SPDX-License-Identifier: GPL-3.0-or-later
 * Copyright (C) 2026 Denis
 */
import { rttChart } from "../chart.js";
import { formatMs, h } from "../dom.js";
import { level, sectionTitle, stats, summaryLine, table } from "../render.js";

export const FAMILY = {
  name: "family",
  label: "IP version",
  type: "segmented",
  options: [
    { value: "auto", label: "Auto" },
    { value: "4", label: "IPv4" },
    { value: "6", label: "IPv6" },
  ],
  default: "auto",
};

export default {
  fields: [
    { name: "host", label: "Host or IP address", type: "text", required: true, placeholder: "e.g. fedoraproject.org or 1.1.1.1", width: "span-2", mono: true },
    { name: "count", label: "Count", type: "number", min: 1, max: 100, step: 1, default: 4, help: "1–100 packets" },
    { name: "interval", label: "Interval (s)", type: "number", min: 0.2, max: 60, step: 0.1, default: 1, help: "At least 0.2 s" },
    { name: "size", label: "Packet size (bytes)", type: "number", min: 0, max: 65507, step: 1, default: 56 },
    FAMILY,
  ],

  verdict: (s) => s.message || "",

  render(s) {
    const lossLevel = s.loss_pct === null || s.loss_pct === undefined ? "neutral" : s.loss_pct === 0 ? "ok" : s.loss_pct >= 100 ? "err" : "warn";
    const nodes = [];
    if (s.message) nodes.push(summaryLine(level(s.status), s.address && s.target !== s.address ? `${s.message} · ${s.target} is ${s.address}` : s.message));
    nodes.push(
      stats([
        { label: "Sent", value: String(s.transmitted ?? 0) },
        { label: "Received", value: String(s.received ?? 0) },
        { label: "Loss", value: s.loss_pct === null || s.loss_pct === undefined ? "–" : `${+Number(s.loss_pct).toFixed(1)} %`, level: lossLevel },
        { label: "Min", value: formatMs(s.min, 2) },
        { label: "Avg", value: formatMs(s.avg, 2) },
        { label: "Max", value: formatMs(s.max, 2) },
        { label: "mdev", value: formatMs(s.mdev, 2) },
      ]),
    );
    if (s.points && s.points.length) nodes.push(rttChart(s.points, { label: `Round-trip time for ${s.points.length} packets` }));
    if (s.icmp_errors && s.icmp_errors.length) {
      nodes.push(
        sectionTitle("ICMP errors"),
        table(
          [
            { key: "seq", label: "Seq", num: true },
            { key: "from", label: "From", mono: true },
            { key: "message", label: "Message" },
          ],
          s.icmp_errors,
        ),
      );
    }
    if (s.duplicates) nodes.push(h("p", { class: "muted" }, `${s.duplicates} duplicate replies received.`));
    return h("div", {}, nodes);
  },
};
