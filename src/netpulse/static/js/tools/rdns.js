/* SPDX-License-Identifier: GPL-3.0-or-later
 * Copyright (C) 2026 Denis
 */
import { dnsStats, recordTable, resolverFields } from "../dnsview.js";
import { h } from "../dom.js";
import { kv, level, sectionTitle, summaryLine } from "../render.js";

export default {
  fields: [
    { name: "address", label: "IP address", type: "text", required: true, placeholder: "e.g. 1.1.1.1 or 2606:4700:4700::1111", width: "span-2", mono: true },
    ...resolverFields(),
  ],
  verdict: (s) => s.message || "",
  render(s) {
    const nodes = [];
    if (s.message) nodes.push(summaryLine(level(s.status), s.message));
    if (!s.rcode) return h("div", {}, nodes);
    nodes.push(dnsStats(s, [{ label: "Server", value: s.server || "–" }]));
    nodes.push(kv([["Reverse name", s.reverse_name], ["Host names", s.names]]));
    nodes.push(sectionTitle("Answer section"), recordTable(s.answer || []));
    return h("div", {}, nodes);
  },
};
