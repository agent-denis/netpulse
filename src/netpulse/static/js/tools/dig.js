/* SPDX-License-Identifier: GPL-3.0-or-later
 * Copyright (C) 2026 Denis
 */
import { details, dnsStats, flagList, resolverFields, sections } from "../dnsview.js";
import { formatMs, h } from "../dom.js";
import { level, notice, sectionTitle, summaryLine, table } from "../render.js";

export const RECORD_TYPES = ["A", "AAAA", "CNAME", "MX", "NS", "TXT", "SOA", "SRV", "CAA", "PTR", "DNSKEY", "DS", "ANY"];

export default {
  fields: [
    { name: "name", label: "Name", type: "text", required: true, placeholder: "e.g. fedoraproject.org", width: "span-2", mono: true, help: "For PTR you can enter an IP address." },
    { name: "type", label: "Record type", type: "select", options: RECORD_TYPES, default: "A" },
    ...resolverFields(),
    {
      type: "checks",
      label: "Options",
      width: "wide",
      items: [
        { name: "short", label: "+short (values only)" },
        { name: "trace", label: "+trace (follow delegation from the root)" },
        { name: "dnssec", label: "+dnssec (request DNSSEC records)" },
        { name: "tcp", label: "TCP" },
      ],
    },
  ],

  verdict: (s) => s.message || "",

  render(s) {
    const nodes = [];
    if (s.message) nodes.push(summaryLine(level(s.status), s.message));
    if (s.short) {
      nodes.push(sectionTitle("Values"));
      nodes.push(s.short.length ? h("pre", { class: "output" }, s.short.join("\n")) : h("p", { class: "muted" }, "No values returned."));
      return h("div", {}, nodes);
    }
    if (!s.rcode) return h("div", {}, nodes);
    nodes.push(dnsStats(s, [{ label: "Server", value: s.server || "–" }, { label: "Protocol", value: s.protocol || "–" }]));
    if (s.ede) nodes.push(notice("warn", h("p", {}, `Extended DNS error: ${s.ede}`)));
    nodes.push(...sections(s));
    if (s.chain && s.chain.length) {
      nodes.push(
        sectionTitle("Delegation path (+trace)"),
        table(
          [
            { key: "step", label: "Step", num: true },
            { key: "server", label: "Answered by", mono: true },
            { key: "zone", label: "Zone / name", mono: true },
            { key: "records", label: "Records", num: true },
            { key: "query_time_ms", label: "Time", num: true, render: (r) => formatMs(r.query_time_ms, 0) },
          ],
          s.chain,
        ),
      );
    }
    nodes.push(
      details([
        ["Flags", flagList(s.flags)],
        ["EDNS flags", flagList(s.edns_flags)],
        ["DNSSEC", s.authenticated ? "validated by the resolver (AD flag)" : null],
        ["Message size", s.message_size],
        ["Question", (s.question || []).map((q) => `${q.name} ${q.class} ${q.type}`)],
      ]),
    );
    return h("div", {}, nodes);
  },
};
