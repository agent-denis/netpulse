/* SPDX-License-Identifier: GPL-3.0-or-later
 * Copyright (C) 2026 Denis
 */
import { dnsStats, recordTable, resolverFields } from "../dnsview.js";
import { h } from "../dom.js";
import { level, sectionTitle, summaryLine } from "../render.js";

export default {
  fields: [
    { name: "name", label: "Name or IP address", type: "text", required: true, placeholder: "e.g. fedoraproject.org", width: "span-2", mono: true },
    { name: "type", label: "Record type", type: "select", options: ["A", "AAAA", "CNAME", "MX", "NS", "TXT", "SOA", "SRV", "CAA", "PTR", "ANY"], default: "A" },
    ...resolverFields(),
  ],

  verdict: (s) => s.message || "",

  render(s) {
    const nodes = [];
    if (s.message) nodes.push(summaryLine(level(s.status), s.message));
    nodes.push(
      dnsStats(s, [
        { label: "Server", value: s.server || "–" },
        { label: "Answer", value: s.answer && s.answer.length ? (s.authoritative ? "Authoritative" : "Non-authoritative") : "–" },
      ]),
    );
    nodes.push(sectionTitle(`Answer (${(s.answer || []).length})`), recordTable(s.answer || [], { withTtl: false, caption: "Answer" }));
    if (s.authority && s.authority.length) {
      nodes.push(sectionTitle(`Authoritative answers can be found from (${s.authority.length})`), recordTable(s.authority, { withTtl: false }));
    }
    return h("div", {}, nodes);
  },
};
