/* SPDX-License-Identifier: GPL-3.0-or-later
 * Copyright (C) <YEAR> <AUTHOR>
 *
 * NetPulse UI entry point.
 */
import { api, ApiError, initToken } from "./api.js";
import { h, replace } from "./dom.js";
import { copyText } from "./export.js";
import { ToolForm } from "./forms.js";
import { initHistory } from "./history.js";
import { icon } from "./icons.js";
import { notice } from "./render.js";
import { ResultCard } from "./results.js";
import { currentPref, initTheme, setPref } from "./theme.js";

const main = document.getElementById("main");
const sidebar = document.getElementById("sidebar");
const live = document.getElementById("live-region");
const alertRegion = document.getElementById("alert-region");

const state = {
  info: null,
  tools: new Map(), // name → {info, def, panel, form, results, cards, navButton, countEl}
  current: null,
};

function announce(text) {
  live.textContent = "";
  // A tick later, so repeated identical messages are still announced.
  setTimeout(() => (live.textContent = text), 50);
}

function alertUser(text) {
  alertRegion.textContent = "";
  setTimeout(() => (alertRegion.textContent = text), 50);
}

function fatal(message, detail) {
  replace(main, notice("err", h("p", {}, h("strong", {}, message)), detail ? h("p", {}, detail) : null));
  sidebar.hidden = true;
}

async function loadDefs(names) {
  const defs = new Map();
  const results = await Promise.allSettled(names.map((n) => import(`./tools/${n}.js`)));
  results.forEach((r, i) => {
    if (r.status === "fulfilled") defs.set(names[i], r.value.default);
    else console.error(`no UI for tool ${names[i]}`, r.reason);
  });
  return defs;
}

// ------------------------------------------------------------------ sidebar
function buildSidebar() {
  const groups = state.info.groups;
  const sections = [];
  for (const group of groups) {
    const tools = [...state.tools.values()].filter((t) => t.info.group === group);
    if (!tools.length) continue;
    const headingId = `nav-${group.toLowerCase().replace(/[^a-z]+/g, "-")}`;
    const items = tools.map((t) => {
      t.countEl = h("span", { class: "run-count", hidden: true, "aria-label": "running jobs" });
      const missing = !t.info.available;
      t.navButton = h(
        "button",
        {
          type: "button",
          class: "nav-item",
          dataset: { tool: t.info.name },
          onclick: () => navigate(t.info.name),
        },
        h("span", { class: "label" }, t.info.title),
        missing ? h("span", { class: "tag" }, icon("missing"), " not installed") : null,
        t.countEl,
      );
      return h("li", {}, t.navButton);
    });
    sections.push(h("section", { "aria-labelledby": headingId }, h("h2", { id: headingId }, group), h("ul", {}, items)));
  }
  replace(sidebar, sections);
  // Up/Down arrows move between tools.
  sidebar.addEventListener("keydown", (ev) => {
    if (ev.key !== "ArrowDown" && ev.key !== "ArrowUp") return;
    const buttons = [...sidebar.querySelectorAll(".nav-item")];
    const i = buttons.indexOf(document.activeElement);
    if (i < 0) return;
    ev.preventDefault();
    buttons[(i + (ev.key === "ArrowDown" ? 1 : buttons.length - 1)) % buttons.length].focus();
  });
}

function updateRunCount(t) {
  const n = t.cards.filter((c) => c.running).length;
  t.countEl.hidden = n === 0;
  t.countEl.textContent = String(n);
  t.countEl.setAttribute("aria-label", `${n} running`);
}

// ------------------------------------------------------------------ panels
function buildPanel(t) {
  const { info, def } = t;
  const headingId = `panel-${info.name}-title`;
  const notes = [];
  if (!info.available) {
    const cmd = info.install_hint;
    const copyBtn = h("button", { type: "button", onclick: async () => announce((await copyText(cmd)) ? "Command copied" : "Copy failed") }, icon("copy"), "Copy command");
    notes.push(
      notice(
        "warn",
        h("p", {}, h("strong", {}, `${info.binaries.join(" / ")} is not installed.`), " Install it with:"),
        h("p", {}, h("code", {}, cmd), " ", copyBtn),
      ),
    );
  }
  for (const n of [...(info.notes || []), ...(def.notes || [])]) notes.push(notice("info", h("p", {}, n)));

  t.form = new ToolForm(info, def, { onSubmit: (values) => run(t, values) });
  t.form.form.addEventListener("keydown", (ev) => {
    if (ev.key === "Enter" && !ev.isComposing && ev.target.tagName !== "BUTTON" && ev.target.tagName !== "TEXTAREA" && ev.target.tagName !== "SUMMARY") {
      ev.preventDefault();
      t.form.form.requestSubmit();
    }
  });
  if (!info.available) t.form.setDisabled(true);
  t.errorBox = h("div", { "aria-live": "polite" });
  t.emptyEl = h("p", { class: "results-empty" }, "Results will appear here. You can run several at once.");
  t.results = h("div", { class: "results", role: "region", "aria-label": `${info.title} results` }, t.emptyEl);
  t.panel = h(
    "section",
    { class: "tool-panel", "aria-labelledby": headingId, hidden: true, dataset: { tool: info.name } },
    h("div", { class: "tool-head" }, h("h2", { id: headingId }, info.title), h("p", {}, info.description)),
    notes,
    t.form.form,
    t.errorBox,
    t.results,
  );
  main.appendChild(t.panel);
}

function select(name, { focus = true } = {}) {
  const t = state.tools.get(name);
  if (!t) return false;
  if (!t.panel) buildPanel(t);
  for (const other of state.tools.values()) {
    if (other.panel) other.panel.hidden = other !== t;
    if (other.navButton) {
      if (other === t) other.navButton.setAttribute("aria-current", "page");
      else other.navButton.removeAttribute("aria-current");
    }
  }
  state.current = t;
  document.title = `${t.info.title} · NetPulse`;
  if (focus) t.form.focusFirst();
  return true;
}

function navigate(name) {
  if (location.hash !== `#/${name}`) history.pushState(null, "", `#/${name}`);
  select(name);
}

function route({ focus = false } = {}) {
  const m = /^#\/([a-z0-9_]+)/.exec(location.hash);
  const first = [...state.tools.keys()][0];
  if (!(m && select(m[1], { focus })) && first) select(first, { focus });
}

// ------------------------------------------------------------------ jobs
function addCard(t, job, { live: isLive }) {
  t.emptyEl.hidden = true;
  const card = new ResultCard(job, {
    def: t.def,
    announce,
    onRerun: (params) => {
      t.form.setValues(params);
      run(t, params);
    },
    onClose: (c) => {
      t.cards = t.cards.filter((x) => x !== c);
      t.emptyEl.hidden = t.cards.length > 0;
      updateRunCount(t);
      t.form.focusFirst();
    },
    onStatus: () => updateRunCount(t),
  });
  t.cards.unshift(card);
  t.results.insertBefore(card.el, t.results.firstChild);
  if (isLive) card.attach();
  updateRunCount(t);
  return card;
}

async function run(t, values) {
  t.form.clearErrors();
  replace(t.errorBox);
  let job;
  try {
    job = await api("POST", "/api/jobs", { tool: t.info.name, params: values });
  } catch (e) {
    if (e instanceof ApiError && e.field && t.form.showError(e.field, e.message)) {
      alertUser(`${e.field}: ${e.message}`);
      return;
    }
    replace(t.errorBox, notice("err", h("p", {}, e.message)));
    alertUser(e.message);
    return;
  }
  announce(`${job.title}: started`);
  addCard(t, job, { live: true });
}

function cancelLatest() {
  const t = state.current;
  if (!t) return false;
  const card = t.cards.find((c) => c.running);
  if (!card) return false;
  announce(`Cancelling ${card.job.title}`);
  card.cancel();
  return true;
}

// ------------------------------------------------------------------ history hooks
function openEntry(entry) {
  const t = state.tools.get(entry.tool);
  if (!t) return;
  navigate(entry.tool);
  t.form.setValues(entry.params);
  const card = addCard(t, entry, { live: false });
  card.renderCommands();
  card.renderSummary();
  card.el.scrollIntoView({ block: "nearest" });
  card.titleEl.tabIndex = -1;
  card.titleEl.focus();
}

function rerunEntry(entry) {
  const t = state.tools.get(entry.tool);
  if (!t) return;
  navigate(entry.tool);
  t.form.setValues(entry.params);
  run(t, entry.params);
}

// ------------------------------------------------------------------ boot
async function boot() {
  initTheme();
  if (!initToken()) {
    fatal(
      "This page was opened without its access token.",
      "Start NetPulse from the application menu or run “netpulse” in a terminal; it opens the right link for you.",
    );
    return;
  }
  try {
    state.info = await api("GET", "/api/info");
  } catch (e) {
    fatal("Could not connect to the NetPulse backend.", e.message);
    return;
  }
  const saved = state.info.settings.theme;
  if (saved && saved !== currentPref()) setPref(saved, { save: false });

  const defs = await loadDefs(state.info.tools.map((t) => t.name));
  for (const info of state.info.tools) {
    if (!defs.has(info.name)) continue;
    state.tools.set(info.name, { info, def: defs.get(info.name), cards: [] });
  }
  document.getElementById("loading")?.remove();
  if (!state.tools.size) {
    fatal("No tools are available.");
    return;
  }
  buildSidebar();
  route({ focus: false });
  window.addEventListener("popstate", () => route({ focus: true }));

  document.addEventListener("keydown", (ev) => {
    if (ev.key !== "Escape" || ev.defaultPrevented) return;
    const openMenu = document.querySelector("details.menu[open]");
    if (openMenu) {
      openMenu.open = false;
      openMenu.querySelector("summary").focus();
      return;
    }
    if (document.querySelector("dialog[open]")) return; // the dialog handles Esc itself
    if (cancelLatest()) ev.preventDefault();
  });
  // Close export menus when clicking elsewhere.
  document.addEventListener("click", (ev) => {
    for (const d of document.querySelectorAll("details.menu[open]")) if (!d.contains(ev.target)) d.open = false;
  });

  initHistory({
    toolTitle: (name) => state.tools.get(name)?.info.title || name,
    openEntry,
    rerunEntry,
    announce,
    settings: state.info.settings,
    historyPath: state.info.history_path,
  });

  // Heartbeat: lets a browser-mode backend notice when the page is gone.
  setInterval(() => api("GET", "/api/ping").catch(() => {}), 20000);
}

boot();
