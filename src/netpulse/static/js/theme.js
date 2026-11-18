/* SPDX-License-Identifier: GPL-3.0-or-later
 * Copyright (C) 2026 Denis
 */
import { api } from "./api.js";

const root = document.documentElement;
const media = window.matchMedia ? window.matchMedia("(prefers-color-scheme: dark)") : null;

function resolve(pref) {
  if (pref === "dark") return "dark";
  if (pref === "light") return "light";
  return media && media.matches ? "dark" : "light";
}

function apply(pref) {
  root.setAttribute("data-theme-pref", pref);
  root.setAttribute("data-theme", resolve(pref));
  for (const input of document.querySelectorAll('#theme-switch input[name="theme"]')) {
    input.checked = input.value === pref;
  }
}

export function currentPref() {
  return root.getAttribute("data-theme-pref") || "system";
}

/** In the native GTK window, keep the window frame in the same theme. */
function tellWindow(pref) {
  const handler = window.webkit && window.webkit.messageHandlers && window.webkit.messageHandlers.netpulse;
  if (handler) handler.postMessage({ type: "theme", value: pref });
}

export async function setPref(pref, { save = true } = {}) {
  apply(pref);
  tellWindow(pref);
  try {
    localStorage.setItem("netpulse-theme", pref);
  } catch (e) {
    /* ignore */
  }
  if (save) {
    try {
      await api("PUT", "/api/settings", { theme: pref });
    } catch (e) {
      /* not fatal: the theme still applies for this session */
    }
  }
}

export function initTheme() {
  apply(currentPref());
  if (media) {
    media.addEventListener("change", () => {
      if (currentPref() === "system") apply("system");
    });
  }
  for (const input of document.querySelectorAll('#theme-switch input[name="theme"]')) {
    input.addEventListener("change", () => {
      if (input.checked) setPref(input.value);
    });
  }
}
