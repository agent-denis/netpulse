/* SPDX-License-Identifier: GPL-3.0-or-later
 * Copyright (C) <YEAR> <AUTHOR>
 *
 * History dialog: browse, search, open, re-run, clear; history preferences.
 */
import { api } from "./api.js";
import { formatDuration, formatTime, h, replace } from "./dom.js";
import { STATUS, statusIcon } from "./icons.js";

export function initHistory({ toolTitle, openEntry, rerunEntry, announce, settings, historyPath }) {
  const dialog = document.getElementById("history-dialog");
  const search = document.getElementById("history-search");
  const tbody = dialog.querySelector("#history-table tbody");
  const statusEl = document.getElementById("history-status");
  const enabled = document.getElementById("history-enabled");
  const max = document.getElementById("history-max");
  const prefs = document.getElementById("history-prefs");
  document.getElementById("history-path").textContent = `Stored in ${historyPath}`;
  enabled.checked = settings.history_enabled;
  max.value = settings.history_max;
  let timer = null;

  async function load() {
    let entries = [];
    try {
      const q = encodeURIComponent(search.value.trim());
      entries = (await api("GET", `/api/history?limit=300&q=${q}`)).entries;
    } catch (e) {
      statusEl.textContent = `Could not load history: ${e.message}`;
      return;
    }
    statusEl.textContent = entries.length
      ? `${entries.length} run${entries.length === 1 ? "" : "s"}${search.value ? " found" : ""}`
      : search.value
        ? "No runs match your search."
        : "No runs yet. Every run you start is saved here.";
    replace(
      tbody,
      entries.map((e) => {
        const st = STATUS[e.status] || STATUS.error;
        const level = e.status === "done" && e.summary && e.summary.status === "warning" ? "warn" : st.cls === "running" ? "neutral" : st.cls;
        return h(
          "tr",
          {},
          h("td", { class: "num" }, formatTime(e.started_at)),
          h("td", {}, toolTitle(e.tool)),
          h("td", { class: "mono" }, (e.title || "").replace(/^[^:]+:\s*/, "")),
          h("td", {}, h("span", { class: ["status-text", level] }, statusIcon(level === "warn" ? "warning" : e.status), level === "warn" ? "Done, with warnings" : st.label)),
          h("td", { class: "num" }, formatDuration(e.elapsed)),
          h(
            "td",
            {},
            h("div", { class: "result-actions" },
              h("button", { type: "button", onclick: () => open(e.id) }, "Open"),
              h("button", { type: "button", onclick: () => { dialog.close(); rerunEntry(e); } }, "Run again"),
            ),
          ),
        );
      }),
    );
  }

  async function open(id) {
    try {
      const entry = await api("GET", `/api/history/${id}`);
      dialog.close();
      openEntry(entry);
    } catch (e) {
      statusEl.textContent = `Could not open entry: ${e.message}`;
    }
  }

  document.getElementById("history-button").addEventListener("click", () => {
    dialog.showModal();
    search.focus();
    load();
  });
  document.getElementById("history-close").addEventListener("click", () => dialog.close());
  search.addEventListener("input", () => {
    clearTimeout(timer);
    timer = setTimeout(load, 200);
  });
  // Clearing asks for confirmation inside the dialog (no window.confirm(): embedded
  // web views do not always show native pop-ups).
  const clearBtn = document.getElementById("history-clear");
  const confirmBox = document.getElementById("history-confirm");
  const confirmText = document.getElementById("history-confirm-text");
  const yes = document.getElementById("history-confirm-yes");
  const no = document.getElementById("history-confirm-no");
  let total = 0;

  function closeConfirm(focusTarget = clearBtn) {
    confirmBox.hidden = true;
    focusTarget.focus();
  }

  clearBtn.addEventListener("click", async () => {
    try {
      total = (await api("GET", "/api/history?limit=1000")).entries.length;
    } catch (e) {
      total = 0;
    }
    if (!total) {
      statusEl.textContent = "History is already empty.";
      return;
    }
    confirmText.textContent =
      total === 1
        ? "Delete the saved run? This cannot be undone."
        : `Delete all ${total}${total >= 1000 ? "+" : ""} saved runs? This cannot be undone.`;
    confirmBox.hidden = false;
    no.focus();
  });
  no.addEventListener("click", () => closeConfirm());
  confirmBox.addEventListener("keydown", (ev) => {
    if (ev.key === "Escape") {
      ev.preventDefault();
      ev.stopPropagation();
      closeConfirm();
    }
  });
  yes.addEventListener("click", async () => {
    yes.disabled = true;
    try {
      await api("DELETE", "/api/history");
      search.value = "";
      await load();
      statusEl.textContent = "History cleared.";
      announce("History cleared");
      closeConfirm(search);
    } catch (e) {
      statusEl.textContent = `Could not clear history: ${e.message}`;
    } finally {
      yes.disabled = false;
    }
  });
  dialog.addEventListener("close", () => (confirmBox.hidden = true));

  prefs.addEventListener("submit", async (ev) => {
    ev.preventDefault();
    try {
      const s = await api("PUT", "/api/settings", { history_enabled: enabled.checked, history_max: Number(max.value) });
      max.value = s.history_max;
      statusEl.textContent = "History settings saved.";
      load();
    } catch (e) {
      statusEl.textContent = `Could not save: ${e.message}`;
    }
  });
}
