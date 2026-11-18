/* SPDX-License-Identifier: GPL-3.0-or-later
 * Copyright (C) <YEAR> <AUTHOR>
 */
import { meter } from "../chart.js";
import { formatMs, h } from "../dom.js";
import { level, stats, statusText, summaryLine, table } from "../render.js";
import { FAMILY } from "./ping.js";

function lossCell(hop) {
  if (hop.loss_pct === null || hop.loss_pct === undefined) return "–";
  const lvl = hop.loss_pct === 0 ? "ok" : hop.loss_pct >= 100 ? "err" : "warn";
  return h("span", {}, meter(hop.loss_pct), statusText(lvl, `${+hop.loss_pct.toFixed(0)} %`));
}

export default {
  fields: [
    { name: "host", label: "Host or IP address", type: "text", required: true, placeholder: "e.g. fedoraproject.org", width: "span-2", mono: true },
    { name: "max_hops", label: "Max hops", type: "number", min: 1, max: 64, step: 1, default: 30 },
    { name: "probes", label: "Probes per hop", type: "number", min: 1, max: 5, step: 1, default: 3 },
    {
      name: "mode",
      label: "Probe type",
      type: "segmented",
      options: [
        { value: "udp", label: "UDP" },
        { value: "icmp", label: "ICMP" },
        { value: "tcp", label: "TCP (root)" },
      ],
      default: "udp",
      help: "TCP needs root privileges.",
    },
    FAMILY,
    { name: "resolve", label: "Resolve hostnames", type: "checkbox", default: true },
  ],

  verdict: (s) => s.message || "",

  render(s) {
    const nodes = [];
    if (s.message) nodes.push(summaryLine(level(s.status), s.message));
    nodes.push(
      stats([
        { label: "Hops", value: String(s.hop_count ?? 0) },
        { label: "Reached", value: s.reached ? "Yes" : "No", level: s.reached ? "ok" : s.status === "error" ? "err" : "warn" },
        { label: "Destination", value: s.address || s.target || "–" },
        { label: "Tool", value: s.backend || "–" },
        s.pmtu ? { label: "Path MTU", value: String(s.pmtu) } : null,
      ]),
    );
    nodes.push(
      table(
        [
          { key: "hop", label: "Hop", num: true },
          { key: "hostname", label: "Hostname", mono: true, render: (r) => (r.hosts.length ? r.hosts.map((x) => x.name || "–").join("\n") : "*") },
          { key: "ip", label: "IP address", mono: true, render: (r) => r.hosts.map((x) => x.ip || "–").join("\n") || "*" },
          { key: "rtts", label: "RTTs", num: true, render: (r) => (r.probes.map((p) => (p.rtt === null || p.rtt === undefined ? "*" : formatMs(p.rtt, 1))).join(", ")) },
          { key: "avg", label: "Avg", num: true, render: (r) => formatMs(r.avg, 1) },
          { key: "loss", label: "Loss", render: lossCell },
          // only when some hop has notes (e.g. !H, asymm), so the table fits narrow windows
          (s.hops || []).some((r) => (r.annotations || []).length)
            ? { key: "annotations", label: "Notes", render: (r) => (r.annotations || []).join(" ") }
            : null,
        ].filter(Boolean),
        s.hops || [],
        { caption: "Hops", empty: "Waiting for the first hop…" },
      ),
    );
    return h("div", {}, nodes);
  },
};
