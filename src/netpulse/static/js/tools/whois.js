/* SPDX-License-Identifier: GPL-3.0-or-later
 * Copyright (C) 2026 Denis
 */
import { h } from "../dom.js";
import { kv, level, stats, summaryLine } from "../render.js";

function dateWithRaw(iso, raw) {
  if (iso) return iso;
  return raw || null;
}

export default {
  fields: [
    { name: "query", label: "Domain, IP address or network", type: "text", required: true, placeholder: "e.g. fedoraproject.org or 8.8.8.8", width: "span-2", mono: true },
  ],
  verdict: (s) => s.message || "",
  render(s) {
    const nodes = [];
    if (s.message) nodes.push(summaryLine(level(s.status), s.message));
    const days = s.days_to_expiry;
    const isNetwork = Boolean(s.netname || s.network);
    if (days !== undefined && days !== null) {
      nodes.push(
        stats([
          { label: "Expires", value: s.expires_date || "–" },
          { label: "Days left", value: String(days), level: days < 0 ? "err" : days < 30 ? "warn" : "ok" },
          s.created_date ? { label: "Registered", value: s.created_date } : null,
        ]),
      );
    }
    nodes.push(
      kv(
        isNetwork
          ? [
              ["Network", s.network],
              ["Name", s.netname],
              ["Organisation", s.org],
              ["Country", s.country],
              ["Abuse contact", s.abuse],
              ["Registered", dateWithRaw(s.created_date, s.created)],
              ["Last changed", dateWithRaw(s.updated_date, s.updated)],
            ]
          : [
              ["Domain", s.domain],
              ["Registrar", s.registrar],
              ["Registered", dateWithRaw(s.created_date, s.created)],
              ["Last changed", dateWithRaw(s.updated_date, s.updated)],
              ["Expires", dateWithRaw(s.expires_date, s.expires)],
              ["Name servers", s.name_servers],
              ["Status", s.status],
              ["DNSSEC", s.dnssec],
              ["Registrant organisation", s.org],
              ["Country", s.country],
              ["Abuse contact", s.abuse],
              ["Registrar whois", s.whois_server],
            ],
      ),
    );
    nodes.push(h("p", { class: "muted" }, "Registries show different fields; the raw output has everything."));
    return h("div", {}, nodes);
  },
};
