"use strict";
// web/admin/admin.js — shared admin SPA bootstrap.
// Exposes: requireAdmin, toast, api, $.

const ADMIN_BASE = "/api/admin";
const COOKIE_NAME = "counselor_admin";

const $ = (sel, root = document) => root.querySelector(sel);

function toast(text, ms = 2500) {
  let el = document.getElementById("toast");
  if (!el) {
    el = document.createElement("div");
    el.id = "toast";
    document.body.appendChild(el);
  }
  el.textContent = text;
  el.classList.remove("hidden");
  clearTimeout(toast._t);
  toast._t = setTimeout(() => el.classList.add("hidden"), ms);
}

async function api(path, options = {}) {
  const opts = {
    credentials: "include",
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
    ...options,
  };
  if (opts.body && typeof opts.body !== "string") {
    opts.body = JSON.stringify(opts.body);
  }
  const r = await fetch(ADMIN_BASE + path, opts);
  if (r.status === 401) {
    // Session expired; bounce to login.
    window.location.href = "/admin/login.html";
    throw new Error("unauthenticated");
  }
  if (!r.ok) {
    let detail = r.statusText;
    try { detail = (await r.json()).detail || detail; } catch (_) {}
    throw Object.assign(new Error(detail), { status: r.status, detail });
  }
  if (r.status === 204) return null;
  return r.json();
}

async function requireAdmin() {
  // For pages other than login.html.
  if (location.pathname.endsWith("/login.html")) return null;
  try {
    const me = await api("/me");
    return me;
  } catch (_) {
    window.location.href = "/admin/login.html";
    return null;
  }
}

// Auto-highlight current nav link.
document.addEventListener("DOMContentLoaded", () => {
  const path = location.pathname;
  for (const a of document.querySelectorAll("nav.admin-nav a")) {
    if (a.getAttribute("href") && path.endsWith(a.getAttribute("href"))) {
      a.classList.add("active");
    }
  }
});