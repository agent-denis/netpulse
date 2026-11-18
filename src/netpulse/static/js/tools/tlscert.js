/* SPDX-License-Identifier: GPL-3.0-or-later
 * Copyright (C) <YEAR> <AUTHOR>
 */
import { h } from "../dom.js";
import { kv, level, sectionTitle, stats, statusText, summaryLine, table } from "../render.js";

function daysLevel(days) {
  if (days === null || days === undefined) return "neutral";
  if (days < 0) return "err";
  if (days < 30) return "warn";
  return "ok";
}

export default {
  fields: [
    { name: "host", label: "Host or IP address", type: "text", required: true, placeholder: "e.g. fedoraproject.org", width: "span-2", mono: true },
    { name: "port", label: "Port", type: "number", min: 1, max: 65535, step: 1, default: 443 },
    { name: "servername", label: "Server name (SNI)", type: "text", placeholder: "default: the host", mono: true, help: "Only needed if it differs from the host." },
  ],
  verdict: (s) => s.message || "",
  render(s) {
    const nodes = [];
    if (s.message) nodes.push(summaryLine(level(s.status), s.message));
    const leaf = s.leaf || {};
    if (!leaf.subject && !(s.chain || []).length) return h("div", {}, nodes);
    nodes.push(
      stats([
        { label: "Trusted", value: s.verify_ok ? "Yes" : s.verify_ok === false ? "No" : "–", level: s.verify_ok ? "ok" : s.verify_ok === false ? "err" : "neutral" },
        { label: "Days left", value: s.days_left === undefined ? "–" : String(s.days_left), level: daysLevel(s.days_left) },
        { label: "Protocol", value: s.protocol || "–" },
        // zero-width spaces let long cipher names wrap after "_" instead of mid-word
        { label: "Cipher", value: (s.cipher || "–").replace(/_/g, "_\u200b"), small: true },
      ]),
    );
    nodes.push(
      kv([
        ["Common name", leaf.common_name],
        ["Subject", leaf.subject],
        ["Alternative names", (leaf.san || []).map((x) => x.replace(/^DNS:/, "").replace(/^IP Address:/, "IP "))],
        ["Issuer", leaf.issuer],
        ["Valid from", s.valid_from ? `${s.valid_from} (${leaf.not_before})` : leaf.not_before],
        ["Valid until", s.expires ? `${s.expires} (${leaf.not_after})` : leaf.not_after],
        ["Verification", s.verify_ok === false ? s.verify_error : s.verify_ok ? "OK: chain and host name are valid" : null],
        ["Serial", leaf.serial],
        ["SHA-256 fingerprint", leaf.sha256],
        ["Server key", s.public_key],
        ["Key exchange", s.temp_key],
      ]),
    );
    if ((s.chain || []).length) {
      nodes.push(
        sectionTitle(`Certificate chain sent by the server (${s.chain.length})`),
        table(
          [
            { key: "depth", label: "#", num: true },
            { key: "subject", label: "Subject", mono: true },
            { key: "issuer", label: "Issuer", mono: true },
            { key: "not_after", label: "Expires", render: (r) => statusText(daysLevel(r.days_left), `${r.not_after || "–"}${r.days_left !== null && r.days_left !== undefined ? ` (${r.days_left} d)` : ""}`) },
            { key: "key", label: "Key" },
          ],
          s.chain,
        ),
      );
    }
    return h("div", {}, nodes);
  },
};
