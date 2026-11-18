/* SPDX-License-Identifier: GPL-3.0-or-later
 * Copyright (C) 2026 Denis
 *
 * Runs synchronously in <head>, before the stylesheet, so the first paint is
 * already in the right theme. The server writes the saved preference into
 * <html data-theme-pref="…">; localStorage is only a fallback (the origin's
 * port is random, so localStorage does not survive restarts).
 */
(function () {
  "use strict";
  var root = document.documentElement;
  var pref = root.getAttribute("data-theme-pref");
  if (pref !== "light" && pref !== "dark" && pref !== "system") {
    pref = "system";
    try {
      var stored = window.localStorage.getItem("netpulse-theme");
      if (stored === "light" || stored === "dark" || stored === "system") pref = stored;
    } catch (e) {
      /* storage disabled: keep the default */
    }
  }
  var dark = pref === "dark" ||
    (pref === "system" && window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches);
  root.setAttribute("data-theme-pref", pref);
  root.setAttribute("data-theme", dark ? "dark" : "light");
})();
