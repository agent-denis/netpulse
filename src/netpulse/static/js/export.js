/* SPDX-License-Identifier: GPL-3.0-or-later
 * Copyright (C) 2026 Denis
 *
 * Copy / export a result as TXT, JSON or Markdown.
 */

function paramsList(params) {
  return Object.entries(params || {})
    .filter(([, v]) => v !== "" && v !== null && v !== undefined && v !== false)
    .map(([k, v]) => [k, typeof v === "object" ? JSON.stringify(v) : String(v)]);
}

function flatSummary(summary) {
  const out = [];
  for (const [k, v] of Object.entries(summary || {})) {
    if (v === null || v === undefined || typeof v === "object") continue;
    out.push([k, String(v)]);
  }
  return out;
}

function commandLines(job) {
  return (job.commands || []).map((argv) => argv.join(" "));
}

export function toText(job) {
  const lines = [`NetPulse: ${job.title}`, `Started: ${new Date(job.started_at * 1000).toISOString()}`];
  lines.push(`Status: ${job.status}${job.message ? ` (${job.message})` : ""}`);
  if (job.exit_code !== null && job.exit_code !== undefined) lines.push(`Exit status: ${job.exit_code}`);
  if (job.elapsed !== undefined) lines.push(`Elapsed: ${Number(job.elapsed).toFixed(2)} s`);
  for (const c of commandLines(job)) lines.push(`Command: ${c}`);
  const sum = flatSummary(job.summary);
  if (sum.length) {
    lines.push("", "Summary:");
    for (const [k, v] of sum) lines.push(`  ${k}: ${v}`);
  }
  lines.push("", "Output:", job.output || "");
  return lines.join("\n");
}

export function toJSON(job) {
  const data = {
    tool: job.tool,
    title: job.title,
    params: job.params,
    started_at: new Date(job.started_at * 1000).toISOString(),
    status: job.status,
    message: job.message,
    exit_code: job.exit_code,
    elapsed_s: job.elapsed,
    commands: job.commands,
    summary: job.summary,
    output: job.output,
  };
  return JSON.stringify(data, null, 2);
}

function mdEscape(text) {
  return String(text).replace(/([\\`*_{}[\]<>|#])/g, "\\$1").replace(/\n/g, " ");
}

function fence(text) {
  let ticks = "```";
  while (String(text).includes(ticks)) ticks += "`";
  return `${ticks}text\n${text}\n${ticks}`;
}

function mdTable(rows, header) {
  if (!rows.length) return "";
  const cols = header || Object.keys(rows[0]);
  const out = [`| ${cols.map(mdEscape).join(" | ")} |`, `| ${cols.map(() => "---").join(" | ")} |`];
  for (const r of rows) {
    out.push(`| ${cols.map((c) => mdEscape(r[c] === null || r[c] === undefined ? "" : typeof r[c] === "object" ? JSON.stringify(r[c]) : r[c])).join(" | ")} |`);
  }
  return out.join("\n");
}

export function toMarkdown(job) {
  const parts = [`# NetPulse: ${mdEscape(job.title)}`, ""];
  parts.push(`- **Started:** ${new Date(job.started_at * 1000).toISOString()}`);
  parts.push(`- **Status:** ${mdEscape(job.status)}${job.message ? ` (${mdEscape(job.message)})` : ""}`);
  if (job.exit_code !== null && job.exit_code !== undefined) parts.push(`- **Exit status:** ${job.exit_code}`);
  if (job.elapsed !== undefined) parts.push(`- **Elapsed:** ${Number(job.elapsed).toFixed(2)} s`);
  for (const c of commandLines(job)) parts.push(`- **Command:** \`${c.replace(/`/g, "'")}\``);
  const params = paramsList(job.params);
  if (params.length) {
    parts.push("", "## Parameters", "", mdTable(params.map(([k, v]) => ({ Parameter: k, Value: v }))));
  }
  const sum = flatSummary(job.summary);
  if (sum.length) {
    parts.push("", "## Summary", "", mdTable(sum.map(([k, v]) => ({ Field: k, Value: v }))));
  }
  for (const [key, value] of Object.entries(job.summary || {})) {
    if (Array.isArray(value) && value.length && typeof value[0] === "object" && value[0] !== null) {
      parts.push("", `### ${mdEscape(key.replace(/_/g, " "))}`, "", mdTable(value));
    }
  }
  parts.push("", "## Raw output", "", fence(job.output || ""), "");
  return parts.join("\n");
}

function slug(text) {
  return String(text).toLowerCase().replace(/[^a-z0-9.-]+/g, "-").replace(/^-+|-+$/g, "").slice(0, 60) || "result";
}

export function download(job, format) {
  const make = { txt: [toText, "text/plain"], json: [toJSON, "application/json"], md: [toMarkdown, "text/markdown"] }[format];
  const blob = new Blob([make[0](job)], { type: `${make[1]};charset=utf-8` });
  const stamp = new Date(job.started_at * 1000).toISOString().replace(/[:]/g, "").replace(/\..+/, "");
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = `netpulse-${slug(job.title)}-${stamp}.${format}`;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(a.href), 10000);
}

export async function copyText(text) {
  try {
    if (navigator.clipboard && window.isSecureContext) {
      await navigator.clipboard.writeText(text);
      return true;
    }
  } catch (e) {
    /* fall through */
  }
  const ta = document.createElement("textarea");
  ta.value = text;
  ta.setAttribute("readonly", "");
  ta.className = "visually-hidden";
  document.body.appendChild(ta);
  ta.select();
  let ok = false;
  try {
    ok = document.execCommand("copy");
  } catch (e) {
    ok = false;
  }
  ta.remove();
  return ok;
}
