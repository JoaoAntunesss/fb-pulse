"use strict";
const $ = (id) => document.getElementById(id);
const el = (tag, cls, text) => { const e = document.createElement(tag); if (cls) e.className = cls; if (text !== undefined) e.textContent = text; return e; };
const SRC = (document.querySelector("meta[name=pulse-data]") || {}).content || "/api/status";
const HOSTED = SRC !== "/api/status";
const NS = "http://www.w3.org/2000/svg";

function spark(values, color) {
  const svg = document.createElementNS(NS, "svg");
  svg.setAttribute("class", "spark"); svg.setAttribute("viewBox", "0 0 200 34"); svg.setAttribute("preserveAspectRatio", "none");
  const pts = values.map((v, i) => [i, v]).filter((p) => p[1] !== null && p[1] !== undefined);
  if (pts.length < 2) return svg;
  const max = Math.max(...pts.map((p) => p[1]), 1), n = Math.max(values.length - 1, 1);
  const d = pts.map((p, i) => (i ? "L" : "M") + (p[0] / n * 200).toFixed(1) + " " + (32 - p[1] / max * 30).toFixed(1)).join(" ");
  const path = document.createElementNS(NS, "path");
  path.setAttribute("d", d); path.setAttribute("fill", "none"); path.setAttribute("stroke", color); path.setAttribute("stroke-width", "1.6");
  svg.appendChild(path);
  return svg;
}

function tile(label, value, sub) {
  const t = el("div", "tile");
  t.appendChild(el("div", "label", label));
  const b = el("div", "big", value === null || value === undefined ? "—" : String(value));
  if (sub) b.appendChild(el("small", "", " " + sub));
  t.appendChild(b);
  return t;
}

function card(p) {
  const c = el("section", "card");
  const h = el("h2"); h.appendChild(el("span", "", p.name)); h.appendChild(el("span", "pill " + p.status, p.status));
  c.appendChild(h);

  const tiles = el("div", "tiles");
  const act = p.active;
  tiles.appendChild(tile("Active now", p.configured.active ? act.value : null));
  tiles.appendChild(tile("Users", p.configured.users ? p.users.value : null));
  tiles.appendChild(tile("Errors 24h", p.configured.errors ? p.errors.count : null));
  c.appendChild(tiles);
  const people = (label, d) => {
    if (!d || d.value === null || d.value === undefined || d.active7 === undefined) return;
    const t2 = el("div", "tiles");
    t2.appendChild(tile(label + " · 7 days", d.active7));
    t2.appendChild(tile(label + " · 30 days", d.active30));
    t2.appendChild(tile("New · 7 days", d.new7));
    c.appendChild(el("div", "label", label === "Installs" ? `Installs (anonymous): ${d.value}` : "Users who opened the app"));
    c.appendChild(t2);
  };
  if (p.configured.users) people("Users", p.users);
  if (p.configured.installs) people("Installs", p.installs);
  const notes = [];
  if (p.configured.active && act.error) notes.push("Active users: " + act.error);
  if (p.configured.users && p.users.error) notes.push("Users: " + p.users.error);
  if (p.configured.errors && p.errors.error) notes.push("Errors: " + p.errors.error);
  if (p.configured.installs && p.installs.error) notes.push("Installs: " + p.installs.error);
  if (!p.configured.active) notes.push("Active users: add ga4_property_id (see SETUP.md)");
  if (!p.configured.errors) notes.push("Errors: add errors_collection (see SETUP.md)");
  if (p.configured.active && act.hist.length > 1) { c.appendChild(el("div", "label", "Active users")); c.appendChild(spark(act.hist, "#4cc9f0")); }

  if (p.urls.length) {
    const r = el("div", "row"); r.appendChild(el("div", "label", "Servers"));
    p.urls.forEach((u) => {
      const line = el("div", "url");
      line.appendChild(el("span", "u", u.url.replace(/^https?:\/\//, "")));
      const l = u.last;
      const m = el("span", "m " + (!l ? "" : !l.ok ? "bad" : l.ms > 2000 ? "warn" : "ok"));
      m.textContent = !l ? "checking…" : l.ok ? `${l.ms} ms` + (u.uptime !== null ? ` · ${u.uptime}%` : "") : (l.error || "down");
      line.appendChild(m); r.appendChild(line);
      r.appendChild(spark(u.ms, l && l.ok ? "#2ee6a6" : "#ff6b6b"));
    });
    c.appendChild(r);
  } else notes.push("Servers: add urls to check (see SETUP.md)");

  if (p.errors.latest && p.errors.latest.length) {
    const r = el("div", "row"); r.appendChild(el("div", "label", "Latest errors"));
    p.errors.latest.forEach((e) => {
      const d = el("div", "err");
      const when = e.ts ? new Date(e.ts).toLocaleString() : "";
      d.appendChild(el("span", "", [when, e.app, e.level].filter(Boolean).join(" · ") + " — "));
      d.appendChild(document.createTextNode(e.message));
      r.appendChild(d);
    });
    c.appendChild(r);
  }
  notes.forEach((n) => c.appendChild(el("div", "note" + (/:\s*(\w+Error|\w+Exception|Permission|403|401)/.test(n) ? " problem" : ""), n)));
  return c;
}

function downloadsCard(d) {
  if (!d || !d.apps || !Object.keys(d.apps).length) return null;
  const c = el("section", "card");
  const h = el("h2"); h.appendChild(el("span", "", "Downloads")); h.appendChild(el("span", "pill up", d.updated || "")); c.appendChild(h);
  const t = el("div", "tiles");
  Object.entries(d.apps).forEach(([name, a]) => t.appendChild(tile(name, a.total, a.last7 === null || a.last7 === undefined ? "" : `+${a.last7} /7d`)));
  c.appendChild(t);
  c.appendChild(el("div", "note", "Release downloads on GitHub (includes your own and in-app updates)."));
  if (d.error) c.appendChild(el("div", "note problem", "Downloads: " + d.error));
  return c;
}

async function refresh() {
  try {
    const r = await fetch(SRC + (HOSTED ? "?t=" + Date.now() : ""), { cache: "no-store" });
    const s = await r.json();
    $("demo").hidden = !s.demo;
    $("slow").textContent = Math.round(s.slow_seconds / 60);
    const grid = $("grid"); grid.replaceChildren(...(downloadsCard(s.downloads) ? [downloadsCard(s.downloads)] : []), ...s.projects.map(card));
    const count = (st) => s.projects.filter((p) => p.status === st).length;
    const sum = $("summary"); sum.replaceChildren();
    [["up", "ok"], ["slow", "warn"], ["down", "bad"]].forEach(([st]) => { if (count(st)) sum.appendChild(el("span", "pill " + st, count(st) + " " + st)); });
    const age = (Date.now() - new Date(s.generated)) / 60000;
    $("stamp").textContent = "Updated " + new Date(s.generated).toLocaleTimeString() + (HOSTED && age > 30 ? " — data is " + Math.round(age) + " min old" : "");
    if (HOSTED) $("foot").textContent = "Hosted copy: a free scheduled job checks your projects about every 10 minutes and publishes this page. Keys stay in GitHub Secrets, never in the page.";
  } catch (e) {
    $("stamp").textContent = HOSTED ? "No data yet — the first scheduled run has not published." : "Cannot reach the local server — is main.py still running?";
  }
}
refresh();
setInterval(refresh, HOSTED ? 60000 : 10000);
