/* SPDX-License-Identifier: GPL-3.0-or-later
 * Copyright (C) 2026 Denis
 *
 * Builds accessible forms from field definitions:
 *   {name, label, type, default, help, placeholder, min, max, step,
 *    options, items, required, width, showIf(values)}
 * type: text | number | select | checkbox | segmented | checks
 */
import { h, nextId } from "./dom.js";
import { icon } from "./icons.js";

function normOptions(options) {
  return (options || []).map((o) => (typeof o === "string" ? { value: o, label: o } : o));
}

export class ToolForm {
  constructor(tool, def, { onSubmit }) {
    this.tool = tool;
    this.def = def;
    this.controls = new Map(); // name → {el, get, set, wrap, error, type}
    this.wraps = [];
    const fieldset = h("fieldset", { class: "fields" }, h("legend", { class: "visually-hidden" }, `${tool.title} options`));
    for (const field of def.fields) fieldset.appendChild(this.build(field));
    this.fieldset = fieldset;
    this.runButton = h("button", { type: "submit", class: "primary" }, icon("play"), "Run");
    this.form = h(
      "form",
      { class: "tool-form card", novalidate: true, "aria-label": `${tool.title} form` },
      fieldset,
      h(
        "div",
        { class: "form-actions" },
        this.runButton,
        h("span", { class: "hint" }, h("kbd", {}, "Enter"), " runs · ", h("kbd", {}, "Esc"), " cancels the latest run"),
      ),
    );
    this.form.addEventListener("submit", (ev) => {
      ev.preventDefault();
      if (!this.form.querySelector("fieldset").disabled) onSubmit(this.values());
    });
    this.form.addEventListener("input", () => this.refresh());
    this.form.addEventListener("change", () => this.refresh());
    this.refresh();
  }

  build(field) {
    const id = nextId(`f-${this.tool.name}-${field.name || "group"}`);
    const helpId = field.help ? `${id}-help` : null;
    const errId = `${id}-err`;
    const error = h("div", { class: "error", id: errId, hidden: true });
    const help = field.help ? h("div", { class: "help", id: helpId }, field.help) : null;
    const describedBy = [helpId, errId].filter(Boolean).join(" ");
    const wrapClass = ["field", field.width];
    let wrap;

    if (field.type === "checks") {
      const items = field.items.map((item) => {
        const cid = nextId(`f-${this.tool.name}-${item.name}`);
        const input = h("input", { type: "checkbox", id: cid, name: item.name });
        input.checked = Boolean(item.default);
        this.controls.set(item.name, {
          el: input,
          type: "checkbox",
          get: () => input.checked,
          set: (v) => (input.checked = Boolean(v)),
          error,
          wrap: null,
        });
        return h("label", { class: "check", for: cid, title: item.help || null }, input, item.label);
      });
      wrap = h(
        "div",
        { class: wrapClass },
        h("fieldset", { "aria-describedby": describedBy }, h("legend", {}, field.label), h("div", { class: "checks" }, items)),
        help,
        error,
      );
      this.wraps.push({ field, wrap });
      return wrap;
    }

    if (field.type === "segmented") {
      const options = normOptions(field.options);
      const radios = [];
      const seg = h("div", { class: "segmented", role: "presentation" });
      for (const opt of options) {
        const rid = nextId(`f-${this.tool.name}-${field.name}`);
        const input = h("input", { type: "radio", id: rid, name: `${this.tool.name}-${field.name}`, value: opt.value });
        input.checked = opt.value === field.default;
        radios.push(input);
        seg.appendChild(input);
        seg.appendChild(h("label", { for: rid }, opt.label));
      }
      wrap = h("div", { class: wrapClass }, h("fieldset", { "aria-describedby": describedBy }, h("legend", {}, field.label), seg), help, error);
      this.controls.set(field.name, {
        el: radios[0],
        type: "segmented",
        get: () => (radios.find((r) => r.checked) || {}).value,
        set: (v) => radios.forEach((r) => (r.checked = r.value === v)),
        error,
        wrap,
      });
      this.wraps.push({ field, wrap });
      return wrap;
    }

    let input;
    if (field.type === "select") {
      input = h("select", { id, name: field.name, "aria-describedby": describedBy });
      for (const opt of normOptions(field.options)) {
        const o = h("option", { value: opt.value }, opt.label);
        if (opt.value === field.default) o.selected = true;
        input.appendChild(o);
      }
    } else if (field.type === "checkbox") {
      input = h("input", { type: "checkbox", id, name: field.name, "aria-describedby": describedBy });
      input.checked = Boolean(field.default);
      wrap = h("div", { class: wrapClass }, h("label", { class: "check", for: id }, input, field.label), help, error);
      this.controls.set(field.name, { el: input, type: "checkbox", get: () => input.checked, set: (v) => (input.checked = Boolean(v)), error, wrap });
      this.wraps.push({ field, wrap });
      return wrap;
    } else {
      input = h("input", {
        type: field.type === "number" ? "number" : "text",
        id,
        name: field.name,
        placeholder: field.placeholder || null,
        min: field.min ?? null,
        max: field.max ?? null,
        step: field.step ?? null,
        required: field.required || null,
        "aria-required": field.required ? "true" : null,
        autocomplete: "off",
        autocapitalize: "off",
        spellcheck: "false",
        inputmode: field.inputmode || null,
        class: field.mono ? "mono" : null,
        "aria-describedby": describedBy,
      });
      if (field.default !== undefined && field.default !== null) input.value = String(field.default);
    }
    wrap = h("div", { class: wrapClass }, h("label", { for: id }, field.label, field.required ? h("span", { "aria-hidden": "true" }, " *") : null), input, help, error);
    this.controls.set(field.name, { el: input, type: field.type, get: () => input.value, set: (v) => (input.value = v ?? ""), error, wrap });
    this.wraps.push({ field, wrap });
    return wrap;
  }

  values() {
    const out = {};
    for (const [name, c] of this.controls) {
      if (c.wrap && c.wrap.hidden) continue;
      let v = c.get();
      if (c.type === "number" && v !== "") v = Number(v);
      out[name] = v;
    }
    return out;
  }

  setValues(params) {
    for (const [name, value] of Object.entries(params || {})) {
      const c = this.controls.get(name);
      if (c && value !== null && value !== undefined) c.set(value);
    }
    this.refresh();
  }

  refresh() {
    const vals = {};
    for (const [name, c] of this.controls) vals[name] = c.get();
    for (const { field, wrap } of this.wraps) {
      if (field.showIf) wrap.hidden = !field.showIf(vals);
    }
  }

  clearErrors() {
    for (const c of this.controls.values()) {
      c.error.hidden = true;
      c.error.textContent = "";
      c.el.removeAttribute("aria-invalid");
    }
  }

  /** Show a server-side validation error next to its field. Returns true if placed. */
  showError(fieldName, message) {
    this.clearErrors();
    const key = fieldName && (this.controls.has(fieldName) ? fieldName : this.def.errorFieldMap?.[fieldName]);
    const c = key ? this.controls.get(key) : null;
    if (!c) return false;
    c.error.hidden = false;
    c.error.replaceChildren(icon("err"), h("span", {}, message));
    c.el.setAttribute("aria-invalid", "true");
    c.el.focus();
    return true;
  }

  setDisabled(disabled) {
    this.fieldset.disabled = disabled;
    this.runButton.disabled = disabled;
  }

  focusFirst() {
    const first = this.form.querySelector("input:not([type=radio]):not([type=checkbox]), select");
    if (first) first.focus();
  }
}
