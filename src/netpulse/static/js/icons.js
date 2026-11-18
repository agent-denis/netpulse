/* SPDX-License-Identifier: GPL-3.0-or-later
 * Copyright (C) <YEAR> <AUTHOR>
 *
 * Original line icons (24×24 grid, stroked). Decorative: always paired with text.
 */
import { s } from "./dom.js";

const PATHS = {
  ok: ["M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18z", "M8 12.5l2.7 2.7L16 9.8"],
  warn: ["M12 3.5L2.5 20h19L12 3.5z", "M12 10v4.5", "M12 17.5h.01"],
  err: ["M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18z", "M9 9l6 6", "M15 9l-6 6"],
  info: ["M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18z", "M12 11v6", "M12 7.5h.01"],
  cancelled: ["M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18z", "M6 18L18 6"],
  clock: ["M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18z", "M12 7v5l3 2"],
  spinner: ["M12 3a9 9 0 1 0 9 9"],
  play: ["M7 4.5v15l12-7.5z"],
  stop: ["M6.5 6.5h11v11h-11z"],
  copy: ["M9 9h11v11H9z", "M5 15H4V4h11v1"],
  download: ["M12 4v11", "M7 10l5 5 5-5", "M4 20h16"],
  close: ["M6 6l12 12", "M18 6L6 18"],
  redo: ["M20 12a8 8 0 1 1-2.3-5.7", "M20 4v5h-5"],
  history: ["M3.5 12a8.5 8.5 0 1 0 2.5-6", "M3 4v4.5h4.5", "M12 8v4.5l3 2"],
  missing: ["M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18z", "M8 12h8"],
  lock: ["M6 11h12v9H6z", "M9 11V8a3 3 0 0 1 6 0v3"],
};

export function icon(name, extraClass = "") {
  const svg = s("svg", {
    class: `icon ${extraClass}`.trim(),
    viewBox: "0 0 24 24",
    "aria-hidden": "true",
    focusable: "false",
  });
  for (const d of PATHS[name] || PATHS.info) svg.appendChild(s("path", { d }));
  return svg;
}

/** Status → {icon, label, cls}. Colour is never the only signal. */
export const STATUS = {
  queued: { icon: "clock", label: "Queued", cls: "neutral" },
  running: { icon: "spinner", label: "Running", cls: "running" },
  done: { icon: "ok", label: "Done", cls: "ok" },
  ok: { icon: "ok", label: "OK", cls: "ok" },
  warning: { icon: "warn", label: "Warning", cls: "warn" },
  failed: { icon: "err", label: "Failed", cls: "err" },
  error: { icon: "err", label: "Error", cls: "err" },
  timeout: { icon: "clock", label: "Timed out", cls: "err" },
  cancelled: { icon: "cancelled", label: "Cancelled", cls: "neutral" },
};

export function statusIcon(status) {
  const st = STATUS[status] || STATUS.error;
  return icon(st.icon, status === "running" ? "spin" : "");
}
