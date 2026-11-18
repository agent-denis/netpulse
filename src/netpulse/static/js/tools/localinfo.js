/* SPDX-License-Identifier: GPL-3.0-or-later
 * Copyright (C) <YEAR> <AUTHOR>
 */
import { h } from "../dom.js";
import { kv, level, notice, sectionTitle, stats, statusText, summaryLine, table } from "../render.js";

function stateText(st) {
  if (st === "UP") return statusText("ok", "up");
  if (st === "DOWN") return statusText("err", "down");
  return statusText("neutral", (st || "unknown").toLowerCase());
}

export default {
  fields: [{ name: "sockets", label: "Also list listening sockets (ss -tuln)", type: "checkbox", default: false, width: "wide" }],
  verdict: (s) => s.message || "",
  render(s) {
    const nodes = [];
    if (s.message) nodes.push(summaryLine(level(s.status), s.message));
    for (const n of s.notes || []) nodes.push(notice("warn", h("p", {}, n)));
    const ifaces = s.interfaces || [];
    nodes.push(
      stats([
        { label: "Interfaces", value: String(ifaces.length) },
        { label: "Default gateway", value: (s.gateways || []).map((g) => g.gateway).filter(Boolean).join(", ") || "none", level: (s.gateways || []).length ? "ok" : "warn" },
        { label: "DNS servers", value: (s.dns_servers || []).join(", ") || "–" },
      ]),
    );
    nodes.push(
      sectionTitle("Interfaces"),
      table(
        [
          { key: "name", label: "Interface", mono: true },
          { key: "state", label: "State", render: (r) => stateText(r.state) },
          { key: "addresses", label: "Addresses", mono: true, render: (r) => r.addresses.map((a) => `${a.address}/${a.prefix}${a.scope && a.scope !== "global" ? ` (${a.scope})` : ""}`).join("\n") || "–" },
          { key: "mac", label: "MAC", mono: true },
          { key: "mtu", label: "MTU", num: true },
        ],
        ifaces,
        { caption: "Interfaces" },
      ),
    );
    nodes.push(
      sectionTitle("Routes"),
      table(
        [
          { key: "family", label: "IP" },
          { key: "dst", label: "Destination", mono: true },
          { key: "gateway", label: "Gateway", mono: true },
          { key: "dev", label: "Interface", mono: true },
          { key: "metric", label: "Metric", num: true },
          { key: "protocol", label: "Source" },
        ],
        s.routes || [],
        { caption: "Routes" },
      ),
    );
    const dns = s.dns || { global: {}, links: [] };
    nodes.push(sectionTitle(`DNS configuration (from ${dns.source || "–"})`));
    const g = dns.global || {};
    nodes.push(kv([["Global DNS servers", g.dns_servers], ["Search domains", g.dns_domain], ["Protocols", g.protocols], ["resolv.conf mode", g["resolv.conf_mode"]]]));
    const links = (dns.links || []).filter((l) => l.dns_servers || l.current_dns_server);
    if (links.length) {
      nodes.push(
        table(
          [
            { key: "link", label: "Interface", mono: true },
            { key: "current_dns_server", label: "Current server", mono: true },
            { key: "dns_servers", label: "DNS servers", mono: true, render: (r) => (r.dns_servers || []).join("\n") },
            { key: "dns_domain", label: "Domains", mono: true, render: (r) => (r.dns_domain || []).join(" ") },
            { key: "default_route", label: "Default route" },
          ],
          links,
          { caption: "DNS per interface" },
        ),
      );
    }
    if (s.sockets) {
      nodes.push(
        sectionTitle(`Listening sockets (${s.sockets.length})`),
        table(
          [
            { key: "proto", label: "Protocol" },
            { key: "address", label: "Address", mono: true },
            { key: "port", label: "Port", num: true },
            { key: "state", label: "State" },
          ],
          s.sockets,
          { caption: "Listening sockets" },
        ),
      );
    }
    return h("div", {}, nodes);
  },
};
