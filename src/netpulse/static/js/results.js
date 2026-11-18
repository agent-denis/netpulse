/* SPDX-License-Identifier: GPL-3.0-or-later
 * Copyright (C) <YEAR> <AUTHOR>
 *
 * A result card: live status, elapsed time, Summary / Raw output tabs,
 * Cancel, Run again, Copy, Export, Close.
 */
import { api, streamJob } from "./api.js";
import { formatDuration, h, nextId, replace } from "./dom.js";
import { copyText, download, toText } from "./export.js";
import { icon, STATUS, statusIcon } from "./icons.js";
import { generic, notice } from "./render.js";

export class ResultCard {
  /**
   * job: snapshot from the API (or a history entry)
   * opts: {def, onRerun(params), onClose(card), announce(text)}
   */
  constructor(job, opts) {
    this.job = { output: "", ...job };
    this.opts = opts;
    this.def = opts.def || {};
    this.stream = null;
    this.timer = null;
    this.renderQueued = false;
    this.build();
    this.setStatus(job.status, job.message);
  }

  get running() {
    return this.job.status === "running" || this.job.status === "queued";
  }

  build() {
    const id = nextId("result");
    this.titleEl = h("h3", { id: `${id}-title`, title: this.job.title }, this.job.title);
    this.badge = h("span", { class: "badge" });
    this.elapsedEl = h("span", { class: "elapsed" }, "0.0 s");
    this.exitEl = h("span", { class: "exit" });
    this.startedEl = h("span", { class: "started" }, new Date(this.job.started_at * 1000).toLocaleTimeString());

    this.cancelBtn = h("button", { type: "button", class: "danger", onclick: () => this.cancel() }, icon("stop"), "Cancel");
    this.rerunBtn = h("button", { type: "button", onclick: () => this.opts.onRerun(this.job.params) }, icon("redo"), "Run again");
    this.copyBtn = h("button", { type: "button", onclick: () => this.copy() }, icon("copy"), "Copy");
    const exportMenu = h(
      "details",
      { class: "menu" },
      h("summary", {}, icon("download"), "Export"),
      h(
        "div",
        { class: "menu-items" },
        [["txt", "Text (.txt)"], ["json", "JSON (.json)"], ["md", "Markdown (.md)"]].map(([fmt, label]) =>
          h("button", { type: "button", onclick: () => { exportMenu.open = false; download(this.job, fmt); } }, label),
        ),
      ),
    );
    this.exportMenu = exportMenu;
    const closeBtn = h(
      "button",
      { type: "button", class: "flat icon-only", "aria-label": `Close result ${this.job.title}`, title: "Close", onclick: () => this.close() },
      icon("close"),
    );

    const tabSum = nextId("tab");
    const tabRaw = nextId("tab");
    this.summaryPanel = h("div", { class: "tab-panel", role: "tabpanel", id: `${tabSum}-panel`, "aria-labelledby": tabSum, tabindex: "0" });
    this.outputEl = h("pre", { class: "output", tabindex: "0", "aria-label": "Raw output" });
    this.outputText = document.createTextNode(this.job.output || "");
    this.outputEl.appendChild(this.outputText);
    this.rawPanel = h("div", { class: "tab-panel", role: "tabpanel", id: `${tabRaw}-panel`, "aria-labelledby": tabRaw, hidden: true }, this.outputEl);
    this.tabs = [
      h("button", { type: "button", role: "tab", id: tabSum, "aria-controls": `${tabSum}-panel`, "aria-selected": "true" }, "Summary"),
      h("button", { type: "button", role: "tab", id: tabRaw, "aria-controls": `${tabRaw}-panel`, "aria-selected": "false", tabindex: "-1" }, "Raw output"),
    ];
    const tablist = h("div", { class: "tabs", role: "tablist", "aria-label": "Result view" }, this.tabs);
    tablist.addEventListener("click", (ev) => {
      const tab = ev.target.closest('[role="tab"]');
      if (tab) this.selectTab(this.tabs.indexOf(tab));
    });
    tablist.addEventListener("keydown", (ev) => {
      const i = this.tabs.indexOf(document.activeElement);
      if (i < 0) return;
      if (ev.key === "ArrowRight" || ev.key === "ArrowLeft") {
        ev.preventDefault();
        const next = (i + (ev.key === "ArrowRight" ? 1 : this.tabs.length - 1)) % this.tabs.length;
        this.selectTab(next);
        this.tabs[next].focus();
      }
    });
    this.cmdEl = h("div", { class: "result-cmd" });

    this.el = h(
      "article",
      { class: "card result", "aria-labelledby": `${id}-title`, dataset: { job: this.job.id } },
      h(
        "header",
        { class: "result-head" },
        h("div", { class: "result-title" }, this.titleEl, this.badge),
        h("div", { class: "result-meta" }, this.startedEl, this.elapsedEl, this.exitEl),
        h("div", { class: "result-actions" }, this.cancelBtn, this.rerunBtn, this.copyBtn, exportMenu, closeBtn),
      ),
      tablist,
      this.summaryPanel,
      this.rawPanel,
      this.cmdEl,
    );
    this.renderSummary();
    this.renderCommands();
  }

  selectTab(index) {
    this.tabs.forEach((t, i) => {
      const selected = i === index;
      t.setAttribute("aria-selected", String(selected));
      t.tabIndex = selected ? 0 : -1;
    });
    this.summaryPanel.hidden = index !== 0;
    this.rawPanel.hidden = index !== 1;
  }

  setStatus(status, message) {
    this.job.status = status;
    if (message !== undefined) this.job.message = message;
    const st = STATUS[status] || STATUS.error;
    let label = st.label;
    // A finished run whose summary says "error" (e.g. 100% loss) is a failure.
    if (status === "done" && this.job.summary && this.job.summary.status === "warning") label = "Done, with warnings";
    const cls = status === "done" && this.job.summary && this.job.summary.status === "warning" ? "warn" : st.cls;
    replace(this.badge, statusIcon(status === "done" && cls === "warn" ? "warning" : status), label);
    this.badge.className = `badge ${cls}`;
    this.badge.title = this.job.message || label;
    this.cancelBtn.hidden = !this.running;
    if (this.running && !this.timer) {
      const t0 = performance.now() - (this.job.elapsed || 0) * 1000;
      this.timer = setInterval(() => {
        this.elapsedEl.textContent = formatDuration((performance.now() - t0) / 1000);
      }, 100);
    } else if (!this.running && this.timer) {
      clearInterval(this.timer);
      this.timer = null;
    }
    if (!this.running) {
      this.elapsedEl.textContent = formatDuration(this.job.elapsed || 0);
      const code = this.job.exit_code;
      this.exitEl.textContent = code === null || code === undefined ? "" : `exit status ${code}`;
    }
    if (this.opts.onStatus) this.opts.onStatus(this);
  }

  renderCommands() {
    const cmds = this.job.commands || [];
    replace(this.cmdEl, cmds.length ? cmds.map((argv) => h("div", {}, h("code", {}, `$ ${argv.join(" ")}`))) : null);
  }

  renderSummary() {
    this.renderQueued = false;
    const nodes = [];
    if (this.job.message && !this.running && this.job.status !== "done") {
      nodes.push(notice(this.job.status === "cancelled" ? "info" : "err", h("p", {}, this.job.message)));
    }
    const summary = this.job.summary || {};
    if (Object.keys(summary).length) {
      try {
        nodes.push(this.def.render ? this.def.render(summary, this.job) : generic(summary));
      } catch (e) {
        console.error(e);
        nodes.push(generic(summary));
      }
    } else if (this.running) {
      nodes.push(h("p", { class: "muted" }, "Waiting for results…"));
    } else if (!nodes.length) {
      nodes.push(h("p", { class: "muted" }, "No summary available. See the raw output."));
    }
    replace(this.summaryPanel, nodes);
  }

  queueRender() {
    if (this.renderQueued) return;
    this.renderQueued = true;
    requestAnimationFrame(() => this.renderSummary());
  }

  appendOutput(text) {
    const pre = this.outputEl;
    const atBottom = pre.scrollHeight - pre.scrollTop - pre.clientHeight < 24;
    this.job.output += text;
    this.outputText.appendData(text);
    if (atBottom) pre.scrollTop = pre.scrollHeight;
  }

  attach() {
    this.stream = streamJob(this.job.id, {
      output: (ev) => this.appendOutput(ev.text),
      summary: (ev) => {
        this.job.summary = ev.data;
        this.queueRender();
      },
      status: (ev) => this.setStatus(ev.status, ev.message),
      end: (ev) => this.finish(ev),
      error: () => {
        if (this.running) {
          this.finish({ status: "error", message: "lost connection to NetPulse", exit_code: null, elapsed: this.job.elapsed, summary: this.job.summary });
        }
      },
    });
  }

  async finish(ev) {
    this.job.summary = ev.summary || this.job.summary;
    this.job.exit_code = ev.exit_code;
    this.job.elapsed = ev.elapsed;
    this.setStatus(ev.status, ev.message);
    try {
      const full = await api("GET", `/api/jobs/${this.job.id}`);
      this.job.commands = full.commands;
      if (full.output.length > this.job.output.length) {
        this.job.output = full.output;
        this.outputText.data = full.output;
      }
    } catch (e) {
      /* keep what we streamed */
    }
    this.renderCommands();
    this.renderSummary();
    const verdict = this.def.verdict ? this.def.verdict(this.job.summary || {}) : "";
    this.opts.announce(`${this.job.title}: ${(STATUS[ev.status] || STATUS.error).label.toLowerCase()}${verdict ? `. ${verdict}` : ""}`);
  }

  async cancel() {
    if (!this.running) return;
    this.cancelBtn.disabled = true;
    try {
      await api("DELETE", `/api/jobs/${this.job.id}`);
    } catch (e) {
      /* the end event will tell */
    } finally {
      this.cancelBtn.disabled = false;
    }
  }

  async copy() {
    const ok = await copyText(toText(this.job));
    this.opts.announce(ok ? "Result copied to the clipboard" : "Copying failed");
    const label = this.copyBtn.lastChild;
    label.textContent = ok ? "Copied" : "Copy failed";
    setTimeout(() => (label.textContent = "Copy"), 1500);
  }

  close() {
    if (this.running) this.cancel();
    if (this.stream) this.stream.close();
    if (this.timer) clearInterval(this.timer);
    this.el.remove();
    this.opts.onClose(this);
  }
}
