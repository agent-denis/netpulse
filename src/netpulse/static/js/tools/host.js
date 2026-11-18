/* SPDX-License-Identifier: GPL-3.0-or-later
 * Copyright (C) <YEAR> <AUTHOR>
 */
import { recordTable, rcodeLevel, resolverFields } from "../dnsview.js";
import { h } from "../dom.js";
import { level, stats, summaryLine } from "../render.js";

export default {
  fields: [
    { name: "name", label: "Name or IP address", type: "text", required: true, placeholder: "e.g. fedoraproject.org", width: "span-2", mono: true },
    {
      name: "type",
      label: "Record type",
      type: "select",
      options: [{ value: "default", label: "Default (A, AAAA, MX)" }, ...["A", "AAAA", "CNAME", "MX", "NS", "TXT", "SOA", "SRV", "CAA", "PTR", "ANY"]],
      default: "default",
    },
    ...resolverFields(),
  ],
  verdict: (s) => s.message || "",
  render(s) {
    const nodes = [];
    if (s.message) nodes.push(summaryLine(level(s.status), s.message));
    nodes.push(
      stats([
        { label: "Status", value: s.rcode || "–", level: rcodeLevel(s.rcode) },
        { label: "Records", value: String(s.answer_count ?? 0) },
        s.server ? { label: "Server", value: s.server } : null,
      ]),
    );
    nodes.push(recordTable(s.records || [], { withTtl: false, caption: "Records" }));
    if (s.missing && s.missing.length) nodes.push(h("p", { class: "muted" }, `No ${s.missing.join(", ")} record.`));
    return h("div", {}, nodes);
  },
};
