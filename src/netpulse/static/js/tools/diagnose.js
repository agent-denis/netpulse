/* SPDX-License-Identifier: GPL-3.0-or-later
 * Copyright (C) <YEAR> <AUTHOR>
 */
import { rttChart } from "../chart.js";
import { h } from "../dom.js";
import { level, sectionTitle, statusText, summaryLine, table } from "../render.js";

const LEVEL = { ok: "ok", warning: "warn", error: "err", running: "neutral", skipped: "neutral" };
const LABEL = { ok: "OK", warning: "Warning", error: "Problem", running: "Running…", skipped: "Skipped" };

export default {
  fields: [{ name: "host", label: "Host or IP address", type: "text", required: true, placeholder: "e.g. fedoraproject.org", width: "span-2", mono: true }],
  verdict: (s) => s.message || "",
  render(s) {
    const nodes = [];
    if (s.message && !(s.pending || []).length) nodes.push(summaryLine(level(s.status), `${s.host}: ${s.message}`));
    nodes.push(
      table(
        [
          { key: "title", label: "Check" },
          { key: "status", label: "Result", render: (r) => statusText(LEVEL[r.status] || "err", LABEL[r.status] || r.status) },
          { key: "finding", label: "Finding" },
        ],
        s.rows || [],
        { caption: "Diagnosis" },
      ),
    );
    const ping = s.checks && s.checks.ping;
    if (ping && ping.points && ping.points.length) nodes.push(sectionTitle("Ping"), rttChart(ping.points));
    nodes.push(h("p", { class: "muted" }, "Each check's full output is in the Raw output tab. For details, run the individual tool."));
    return h("div", {}, nodes);
  },
};
