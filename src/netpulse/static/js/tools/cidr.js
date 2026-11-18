/* SPDX-License-Identifier: GPL-3.0-or-later
 * Copyright (C) <YEAR> <AUTHOR>
 */
import { h } from "../dom.js";
import { kv, sectionTitle, stats, table } from "../render.js";

export default {
  fields: [
    { name: "network", label: "Network or address", type: "text", required: true, placeholder: "e.g. 192.168.1.0/24, 10.0.0.1 255.0.0.0 or 2001:db8::/48", width: "span-2", mono: true },
    { name: "split", label: "Split into subnets of /", type: "number", min: 1, max: 128, step: 1, placeholder: "optional, e.g. 26", help: "Optional: list the smaller subnets." },
  ],
  verdict: (s) => s.message || "",
  render(s) {
    const nodes = [];
    nodes.push(
      stats([
        { label: "Network", value: s.network },
        { label: "Addresses", value: s.total_addresses, small: true },
        s.version === 4 ? { label: "Usable hosts", value: s.usable_hosts } : { label: "Size", value: s.size },
        { label: "Type", value: (s.address_kind || []).join(", "), small: true },
      ]),
    );
    if (s.note) nodes.push(h("p", { class: "muted" }, s.note));
    nodes.push(
      kv(
        s.version === 4
          ? [
              ["Network address", s.network],
              ["Netmask", s.netmask],
              ["Netmask (binary)", s.netmask_bits],
              ["Wildcard mask", s.wildcard],
              ["Broadcast", s.broadcast],
              ["First host", s.first_host],
              ["Last host", s.last_host],
              ["Prefix length", `/${s.prefix}`],
              ["Reverse DNS zone", s.reverse_zone],
            ]
          : [
              ["Network", s.network],
              ["First address", s.first_address],
              ["Last address", s.last_address],
              ["Address (expanded)", s.expanded],
              ["Address (compressed)", s.compressed],
              ["Prefix length", `/${s.prefix}`],
              ["Reverse DNS zone", s.reverse_zone],
            ],
      ),
    );
    if (s.subnets) {
      nodes.push(
        sectionTitle(`Subnets (${s.subnet_count}${s.subnets_truncated ? `, first ${s.subnets.length} shown` : ""})`),
        table(
          [
            { key: "subnet", label: "Subnet", mono: true },
            { key: "first", label: "First", mono: true },
            { key: "last", label: "Last", mono: true },
            { key: "addresses", label: "Addresses", num: true },
          ],
          s.subnets,
        ),
      );
    }
    return h("div", {}, nodes);
  },
};
