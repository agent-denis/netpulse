/* SPDX-License-Identifier: GPL-3.0-or-later
 * Copyright (C) <YEAR> <AUTHOR>
 *
 * Tiny DOM helper. Text always goes in via text nodes / textContent, so tool
 * output can never become markup. (There is deliberately no innerHTML in
 * this code base; a test enforces that.)
 */

const SVG_NS = "http://www.w3.org/2000/svg";

function append(el, child) {
  if (child === null || child === undefined || child === false) return;
  if (Array.isArray(child)) {
    child.forEach((c) => append(el, c));
  } else if (child instanceof Node) {
    el.appendChild(child);
  } else {
    el.appendChild(document.createTextNode(String(child)));
  }
}

function setAttrs(el, attrs) {
  for (const [key, value] of Object.entries(attrs || {})) {
    if (value === null || value === undefined || value === false) continue;
    if (key === "class") el.setAttribute("class", Array.isArray(value) ? value.filter(Boolean).join(" ") : value);
    else if (key === "dataset") Object.assign(el.dataset, value);
    else if (key.startsWith("on") && typeof value === "function") el.addEventListener(key.slice(2), value);
    else if (key === "text") el.textContent = String(value);
    else if (value === true) el.setAttribute(key, "");
    else el.setAttribute(key, String(value));
  }
}

/** h("div", {class: "x"}, "text", child, [more]) */
export function h(tag, attrs, ...children) {
  const el = document.createElement(tag);
  setAttrs(el, attrs);
  append(el, children);
  return el;
}

/** Same as h() but in the SVG namespace. */
export function s(tag, attrs, ...children) {
  const el = document.createElementNS(SVG_NS, tag);
  setAttrs(el, attrs);
  append(el, children);
  return el;
}

export function clear(el) {
  while (el.firstChild) el.removeChild(el.firstChild);
  return el;
}

export function replace(el, ...children) {
  clear(el);
  append(el, children);
  return el;
}

let uid = 0;
export function nextId(prefix = "id") {
  uid += 1;
  return `${prefix}-${uid}`;
}

export function formatMs(value, digits = 1) {
  if (value === null || value === undefined || Number.isNaN(value)) return "–";
  if (value >= 1000) return `${(value / 1000).toFixed(2)} s`;
  return `${Number(value).toFixed(digits)} ms`;
}

export function formatDuration(seconds) {
  if (seconds === null || seconds === undefined) return "–";
  if (seconds < 60) return `${seconds.toFixed(1)} s`;
  const m = Math.floor(seconds / 60);
  return `${m} min ${Math.round(seconds - m * 60)} s`;
}

export function formatTime(epochSeconds) {
  const d = new Date(epochSeconds * 1000);
  return d.toLocaleString(undefined, { dateStyle: "medium", timeStyle: "medium" });
}
