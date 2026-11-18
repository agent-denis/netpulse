/* SPDX-License-Identifier: GPL-3.0-or-later
 * Copyright (C) <YEAR> <AUTHOR>
 */
import { rcodeLevel, ttlText } from "../dnsview.js";
import { formatMs, h } from "../dom.js";
import { level, statusText, summaryLine, table } from "../render.js";
import { RECORD_TYPES } from "./dig.js";

const LABELS = { system: "System resolver", "1.1.1.1": "Cloudflare 1.1.1.1", "8.8.8.8": "Google 8.8.8.8", "9.9.9.9": "Quad9 9.9.9.9" };

export default {
  fields: [
    { name: "name", label: "Name", type: "text", required: true, placeholder: "e.g. fedoraproject.org", width: "span-2", mono: true },
    { name: "type", label: "Record type", type: "select", options: RECORD_TYPES.filter((t) => t !== "ANY"), default: "A" },
    {
      type: "checks",
      label: "Resolvers",
      width: "wide",
      items: [
        { name: "use_system", label: "System resolver" },
        { name: "use_1_1_1_1", label: "Cloudflare (1.1.1.1)", default: true },
        { name: "use_8_8_8_8", label: "Google (8.8.8.8)", default: true },
        { name: "use_9_9_9_9", label: "Quad9 (9.9.9.9)", default: true },
      ],
    },
    { name: "custom", label: "More resolvers", type: "text", placeholder: "e.g. 192.168.1.1 ns1.example.net", width: "span-2", mono: true, help: "Optional. Separate with spaces; up to 8 resolvers in total." },
  ],
  errorFieldMap: { resolvers: "custom" },
  verdict: (s) => s.message || "",
  render(s) {
    const nodes = [];
    if (s.message) nodes.push(summaryLine(level(s.status), s.message));
    const rows = [...(s.rows || []), ...(s.pending || []).map((r) => ({ resolver: r, pending: true }))];
    nodes.push(
      table(
        [
          { key: "resolver", label: "Resolver", render: (r) => LABELS[r.resolver] || r.resolver },
          {
            key: "rcode",
            label: "Status",
            render: (r) => (r.pending ? statusText("neutral", "waiting…") : statusText(rcodeLevel(r.rcode) === "ok" ? "ok" : rcodeLevel(r.rcode), r.rcode || r.message || "error")),
          },
          { key: "answers", label: "Answer", mono: true, render: (r) => (r.pending ? "" : r.answers && r.answers.length ? r.answers.join("\n") : "(none)") },
          { key: "min_ttl", label: "TTL", num: true, render: (r) => (r.pending ? "" : ttlText(r.min_ttl)) },
          { key: "query_time_ms", label: "Time", num: true, render: (r) => (r.pending ? "" : formatMs(r.query_time_ms, 0)) },
          {
            key: "matches",
            label: "Same as most?",
            render: (r) => (r.pending ? "" : r.matches ? statusText("ok", "Same") : statusText("warn", "Different")),
          },
        ],
        rows,
        { caption: "Answers per resolver", rowClass: (r) => (!r.pending && r.matches === false ? "diff" : null) },
      ),
    );
    nodes.push(h("p", { class: "muted" }, "Answers are compared without TTLs, which naturally differ between caches."));
    return h("div", {}, nodes);
  },
};
