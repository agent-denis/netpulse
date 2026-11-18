/* SPDX-License-Identifier: GPL-3.0-or-later
 * Copyright (C) <YEAR> <AUTHOR>
 */
import { formatMs, h } from "../dom.js";
import { kv, level, statusText, summaryLine, table } from "../render.js";
import { FAMILY } from "./ping.js";

const STATE = { open: "ok", closed: "neutral", filtered: "warn", error: "err" };

export default {
  fields: [
    { name: "host", label: "Host or IP address", type: "text", required: true, placeholder: "e.g. fedoraproject.org", width: "span-2", mono: true },
    {
      name: "preset",
      label: "Ports",
      type: "segmented",
      options: [
        { value: "web", label: "Web" },
        { value: "mail", label: "Mail" },
        { value: "ssh", label: "SSH" },
        { value: "custom", label: "Custom" },
      ],
      default: "web",
    },
    { name: "ports", label: "Port numbers", type: "text", placeholder: "e.g. 22, 80, 443", default: "22, 80, 443", showIf: (v) => v.preset === "custom", help: "Up to 10 ports, separated by commas.", mono: true },
    { name: "timeout", label: "Timeout per port (s)", type: "number", min: 0.5, max: 10, step: 0.5, default: 3 },
    FAMILY,
  ],
  verdict: (s) => s.message || "",
  render(s) {
    const nodes = [];
    if (s.message) nodes.push(summaryLine(level(s.status), s.message));
    nodes.push(kv([["Host", s.host], ["Address used", s.address], ["Other addresses", s.other_addresses]]));
    nodes.push(
      table(
        [
          { key: "port", label: "Port", num: true },
          { key: "service", label: "Service" },
          { key: "state", label: "State", render: (r) => statusText(STATE[r.state] || "err", r.state) },
          { key: "time_ms", label: "Connect time", num: true, render: (r) => (r.time_ms === null ? "–" : formatMs(r.time_ms, 1)) },
          { key: "detail", label: "Details" },
        ],
        s.results || [],
        { caption: "Port results", empty: "Checking…" },
      ),
    );
    nodes.push(h("p", { class: "muted" }, "Open = something accepted the connection. Closed = the host refused it. Filtered = no answer (often a firewall)."));
    return h("div", {}, nodes);
  },
};
