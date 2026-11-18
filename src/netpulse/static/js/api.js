/* SPDX-License-Identifier: GPL-3.0-or-later
 * Copyright (C) 2026 Denis
 *
 * Talking to the local backend. The access token arrives in the URL
 * fragment (#token=…), which browsers never send to the server and which we
 * remove from the address bar immediately; it is kept in sessionStorage so
 * reloading the tab keeps working.
 */

const TOKEN_KEY = "netpulse-token";
let token = "";

export class ApiError extends Error {
  constructor(status, message, field) {
    super(message);
    this.status = status;
    this.field = field || null;
  }
}

export function initToken() {
  const match = /(?:^#|&)token=([A-Za-z0-9_-]+)/.exec(window.location.hash);
  if (match) {
    token = match[1];
    try {
      sessionStorage.setItem(TOKEN_KEY, token);
    } catch (e) {
      /* ignore */
    }
    history.replaceState(null, "", window.location.pathname + window.location.search);
  } else {
    try {
      token = sessionStorage.getItem(TOKEN_KEY) || "";
    } catch (e) {
      token = "";
    }
  }
  return token !== "";
}

export async function api(method, path, body) {
  const opts = { method, headers: { "X-NetPulse-Token": token }, cache: "no-store" };
  if (body !== undefined) {
    opts.headers["Content-Type"] = "application/json";
    opts.body = JSON.stringify(body);
  }
  let resp;
  try {
    resp = await fetch(path, opts);
  } catch (e) {
    throw new ApiError(0, "NetPulse backend is not reachable (was it closed?)");
  }
  let data = null;
  try {
    data = await resp.json();
  } catch (e) {
    data = null;
  }
  if (!resp.ok) {
    throw new ApiError(resp.status, (data && data.error) || `HTTP ${resp.status}`, data && data.field);
  }
  return data;
}

/**
 * Subscribe to a job's Server-Sent Events.
 * handlers: {output(ev), summary(ev), status(ev), end(ev), error()}
 */
export function streamJob(jobId, handlers) {
  const url = `/api/jobs/${encodeURIComponent(jobId)}/events?token=${encodeURIComponent(token)}`;
  const source = new EventSource(url);
  let finished = false;
  for (const type of ["output", "summary", "status", "end"]) {
    source.addEventListener(type, (msg) => {
      let ev;
      try {
        ev = JSON.parse(msg.data);
      } catch (e) {
        return;
      }
      if (type === "end") {
        finished = true;
        source.close();
      }
      if (handlers[type]) handlers[type](ev);
    });
  }
  source.onerror = () => {
    if (finished) return;
    if (source.readyState === EventSource.CLOSED && handlers.error) handlers.error();
  };
  return {
    close() {
      finished = true;
      source.close();
    },
  };
}
