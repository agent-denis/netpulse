/* SPDX-License-Identifier: GPL-3.0-or-later
 * Copyright (C) 2026 Denis
 *
 * Shared DNS form fields and record tables.
 */
import { formatMs, h } from "./dom.js";
import { kv, sectionTitle, stats, table } from "./render.js";

export const RESOLVER_OPTIONS = [
  { value: "system", label: "System resolver" },
  { value: "1.1.1.1", label: "Cloudflare (1.1.1.1)" },
  { value: "8.8.8.8", label: "Google (8.8.8.8)" },
  { value: "9.9.9.9", label: "Quad9 (9.9.9.9)" },
  { value: "custom", label: "Custom…" },
];

export function resolverFields() {
  return [
    { name: "resolver", label: "Resolver", type: "select", options: RESOLVER_OPTIONS, default: "system" },
    {
      name: "custom",
      label: "Custom resolver",
      type: "text",
      placeholder: "e.g. 192.168.1.1 or dns.example.net",
      showIf: (v) => v.resolver === "custom",
      mono: true,
    },
  ];
}

const FLAG_NAMES = {
  qr: "response",
  aa: "authoritative answer",
  tc: "truncated",
  rd: "recursion desired",
  ra: "recursion available",
  ad: "authenticated data (DNSSEC)",
  cd: "checking disabled",
  do: "DNSSEC OK",
};

export function flagList(flags) {
  if (!flags || !flags.length) return null;
  return flags.map((f) => `${f} (${FLAG_NAMES[f] || "?"})`).join(", ");
}

export function rcodeLevel(rcode) {
  if (rcode === "NOERROR") return "ok";
  if (rcode === "NXDOMAIN" || rcode === "YXDOMAIN") return "warn";
  if (!rcode) return "neutral";
  return "err";
}

export function ttlText(ttl) {
  if (ttl === null || ttl === undefined) return "–";
  if (ttl < 120) return `${ttl} s`;
  if (ttl < 7200) return `${ttl} s (${Math.round(ttl / 60)} min)`;
  if (ttl < 172800) return `${ttl} s (${Math.round(ttl / 3600)} h)`;
  return `${ttl} s (${Math.round(ttl / 86400)} d)`;
}

export function recordTable(records, { withTtl = true, caption = "" } = {}) {
  const cols = [
    { key: "name", label: "Name", mono: true },
    withTtl ? { key: "ttl", label: "TTL", num: true, render: (r) => ttlText(r.ttl) } : null,
    { key: "type", label: "Type" },
    { key: "data", label: "Data", mono: true },
  ].filter(Boolean);
  return table(cols, records, { caption, empty: "No records" });
}

export function dnsStats(summary, extra = []) {
  return stats([
    { label: "Status", value: summary.rcode || "–", level: rcodeLevel(summary.rcode) },
    { label: "Records", value: String(summary.answer_count ?? (summary.answer || []).length) },
    summary.query_time_ms !== undefined && summary.query_time_ms !== null
      ? { label: "Query time", value: formatMs(summary.query_time_ms, 0) }
      : null,
    ...extra,
  ]);
}

export function sections(summary) {
  const out = [];
  for (const [key, title] of [["answer", "Answer"], ["authority", "Authority"], ["additional", "Additional"]]) {
    const recs = summary[key] || [];
    if (key !== "answer" && !recs.length) continue;
    out.push(sectionTitle(`${title} section (${recs.length})`), recordTable(recs, { caption: `${title} section` }));
  }
  return out;
}

export function details(pairs) {
  return h("div", {}, sectionTitle("Details"), kv(pairs));
}
