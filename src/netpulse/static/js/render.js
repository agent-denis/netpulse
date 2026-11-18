/* SPDX-License-Identifier: GPL-3.0-or-later
 * Copyright (C) <YEAR> <AUTHOR>
 *
 * Reusable summary widgets. All values are rendered as text.
 */
import { h } from "./dom.js";
import { icon } from "./icons.js";

const LEVEL_ICON = { ok: "ok", warn: "warn", err: "err", info: "info", neutral: "missing" };

/** {label, value, unit, level} tiles */
export function stats(items) {
  return h(
    "div",
    { class: "stats" },
    items
      .filter((i) => i)
      .map((i) =>
        h(
          "div",
          { class: ["stat", i.level, i.small || (typeof i.value === "string" && i.value.length > 9) ? "small" : null] },
          h("div", { class: "stat-label" }, i.label),
          h(
            "div",
            { class: "stat-value" },
            i.level && i.level !== "neutral" ? [icon(LEVEL_ICON[i.level]), " "] : null,
            i.value ?? "–",
            i.unit ? h("span", { class: "unit" }, i.unit) : null,
          ),
        ),
      ),
  );
}

/** A one-line verdict with icon + text, e.g. "All 4 replies received". */
export function summaryLine(level, text) {
  return h("p", { class: ["summary-line", level] }, icon(LEVEL_ICON[level] || "info"), h("span", {}, text));
}

export function notice(level, ...content) {
  return h("div", { class: ["notice", level], role: level === "err" ? "alert" : null }, icon(LEVEL_ICON[level] || "info"), h("div", {}, ...content));
}

export function statusText(level, text) {
  return h("span", { class: ["status-text", level] }, icon(LEVEL_ICON[level] || "info"), text);
}

export function sectionTitle(text) {
  return h("h4", { class: "section-title" }, text);
}

/** [[key, value], …] → definition list. Null/empty values are skipped. */
export function kv(pairs) {
  const dl = h("dl", { class: "kv" });
  for (const [k, v] of pairs) {
    if (v === null || v === undefined || v === "" || (Array.isArray(v) && v.length === 0)) continue;
    dl.appendChild(h("dt", {}, k));
    dl.appendChild(h("dd", {}, Array.isArray(v) ? v.join(", ") : v));
  }
  return dl;
}

/**
 * columns: [{key, label, num, mono, render(row) → Node|string}]
 * rows: objects. opts: {caption, rowClass(row), empty}
 */
export function table(columns, rows, opts = {}) {
  const thead = h("thead", {}, h("tr", {}, columns.map((c) => h("th", { scope: "col" }, c.label))));
  const tbody = h("tbody");
  for (const row of rows) {
    const tr = h("tr", { class: opts.rowClass ? opts.rowClass(row) : null });
    for (const c of columns) {
      const value = c.render ? c.render(row) : row[c.key];
      tr.appendChild(h("td", { class: [c.num && "num", c.mono && "mono"] }, value === null || value === undefined || value === "" ? "–" : value));
    }
    tbody.appendChild(tr);
  }
  if (!rows.length) {
    tbody.appendChild(h("tr", {}, h("td", { colspan: String(columns.length), class: "muted" }, opts.empty || "No data")));
  }
  return h(
    "div",
    { class: "table-wrap" },
    h("table", { class: "data" }, opts.caption ? h("caption", { class: "visually-hidden" }, opts.caption) : null, thead, tbody),
  );
}

/** Generic fallback: render any summary object as key/value pairs. */
export function generic(summary) {
  const pairs = [];
  for (const [k, v] of Object.entries(summary || {})) {
    if (v === null || typeof v === "object") continue;
    pairs.push([k.replace(/_/g, " "), String(v)]);
  }
  return kv(pairs);
}

/** Verdict level from a summary.status string. */
export function level(status) {
  return { ok: "ok", warning: "warn", error: "err" }[status] || "info";
}
