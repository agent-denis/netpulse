/* SPDX-License-Identifier: GPL-3.0-or-later
 * Copyright (C) 2026 Denis
 */
import { stackedBar } from "../chart.js";
import { formatMs, h } from "../dom.js";
import { kv, level, notice, sectionTitle, stats, statusText, summaryLine, table } from "../render.js";
import { FAMILY } from "./ping.js";

function codeLevel(code) {
  if (!code) return "err";
  if (code >= 500) return "err";
  if (code >= 400 || (code >= 300 && code < 400)) return "warn";
  return "ok";
}

export default {
  fields: [
    { name: "url", label: "URL", type: "text", required: true, placeholder: "e.g. fedoraproject.org or 192.168.1.1:8080/status", width: "span-2", mono: true, help: "Without a scheme, HTTPS is used." },
    { name: "method", label: "Method", type: "segmented", options: ["GET", "HEAD"], default: "GET" },
    { name: "timeout", label: "Timeout (s)", type: "number", min: 1, max: 120, step: 1, default: 20 },
    { name: "max_redirects", label: "Max redirects", type: "number", min: 0, max: 20, step: 1, default: 10, showIf: (v) => v.follow },
    FAMILY,
    {
      type: "checks",
      label: "Options",
      width: "wide",
      items: [
        { name: "follow", label: "Follow redirects", default: true },
        { name: "insecure", label: "Don't verify the TLS certificate (insecure)" },
      ],
    },
  ],
  verdict: (s) => s.message || "",
  render(s) {
    const nodes = [];
    if (s.message) nodes.push(summaryLine(level(s.status), s.message));
    const t = s.timing || {};
    nodes.push(
      stats([
        { label: "Status", value: s.http_code ? String(s.http_code) : "–", level: codeLevel(s.http_code) },
        { label: "Total", value: formatMs(t.total_ms, 0) },
        { label: "Time to first byte", value: formatMs(t.ttfb_ms, 0) },
        { label: "Redirects", value: String(s.num_redirects ?? 0) },
        { label: "HTTP version", value: s.http_version || "–" },
      ]),
    );
    if (t.phases && t.phases.length) {
      nodes.push(sectionTitle("Where the time went"), stackedBar(t.phases.map((p) => ({ label: p.label, value: p.ms }))));
      if (!t.exact) nodes.push(h("p", { class: "muted" }, "With redirects, curl adds its DNS/connect/TLS timers over all requests, so only the split between redirects and the final request is shown. Check the final URL with redirects off for its full breakdown."));
    }
    if (s.ssl_verify_result && s.ssl_verify_result !== "0") {
      nodes.push(notice("warn", h("p", {}, `TLS verification result code: ${s.ssl_verify_result}`)));
    }
    nodes.push(kv([["Final URL", s.url_effective], ["Server address", s.remote_ip ? `${s.remote_ip} port ${s.remote_port}` : null], ["Content type", s.content_type], ["Downloaded", s.size_download ? `${s.size_download.toLocaleString()} bytes` : null]]));
    if ((s.responses || []).length > 1) {
      nodes.push(
        sectionTitle("Redirect chain"),
        table(
          [
            { key: "url", label: "URL", mono: true },
            { key: "status", label: "Status", render: (r) => statusText(codeLevel(r.status), `${r.status} ${r.reason || ""}`.trim()) },
            { key: "location", label: "Redirects to", mono: true },
          ],
          s.responses,
        ),
      );
    }
    if ((s.headers || []).length) {
      nodes.push(
        sectionTitle("Response headers"),
        table(
          [
            { key: "0", label: "Header", mono: true, render: (r) => r[0] },
            { key: "1", label: "Value", mono: true, render: (r) => r[1] },
          ],
          s.headers,
        ),
      );
    }
    return h("div", {}, nodes);
  },
};
