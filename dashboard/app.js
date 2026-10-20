const LABELS = { online: "Online", offline: "Offline", error: "Errore", unknown: "Sconosciuto" };
const STORE = "dashboard.filter";
const NONE = "__none";

let filter = loadFilter();
let current = null;
let last = "";

function loadFilter() {
  try { return localStorage.getItem(STORE) || "all"; } catch { return "all"; }
}

function saveFilter(v) {
  try { localStorage.setItem(STORE, v); } catch { /* ignora */ }
}

function el(tag, cls, text) {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  if (text !== undefined) e.textContent = text;
  return e;
}

function link(cls, text, href) {
  const a = el("a", cls, text);
  a.href = href;
  a.target = "_blank";
  a.rel = "noopener noreferrer";
  return a;
}

function dirButton(path) {
  const btn = el("button", "dir");
  btn.type = "button";
  btn.title = path;
  const hint = el("span", "hint", "Copia");
  btn.append(el("span", "path", path), hint);
  btn.addEventListener("click", async () => {
    try {
      await navigator.clipboard.writeText(path);
      hint.textContent = "Copiato ✓";
    } catch {
      hint.textContent = "Errore";
    }
    setTimeout(() => { hint.textContent = "Copia"; }, 1500);
  });
  return btn;
}

function card(p) {
  const c = el("article", `card ${p.state}`);

  const top = el("div", "top");
  top.append(el("div", "avatar", p.name.charAt(0).toUpperCase()));
  const txt = el("div");
  txt.append(el("div", "name", p.name), el("div", "domain", p.domain));
  top.append(txt);
  c.append(top);

  if (p.routes.length) {
    const routes = el("div", "routes");
    for (const r of p.routes) routes.append(link("route", r.label, r.url));
    c.append(routes);
  }

  if (p.dir) c.append(dirButton(p.dir));

  const bottom = el("div", "bottom");
  const left = el("div", "left");
  const chip = el("span", `chip ${p.state}`, LABELS[p.state] || LABELS.unknown);
  if (p.ms != null && p.state === "online") chip.title = `${p.ms} ms`;
  left.append(chip);
  if (p.label) left.append(el("span", "tag", p.label));
  bottom.append(left, link("btn", "Apri ↗", p.url));
  c.append(bottom);

  return c;
}

const key = p => (p.label ? p.label.toLowerCase() : NONE);

function cmp(a, b) {
  const la = (a.label || "").toLowerCase();
  const lb = (b.label || "").toLowerCase();
  return (b.state === "online") - (a.state === "online")        // 1. online prima
    || (!la !== !lb ? (la ? 1 : -1) : 0)                         // 2. senza etichetta prima
    || la.localeCompare(lb, "it")                                // 3. etichetta
    || a.name.localeCompare(b.name, "it", { sensitivity: "base" }); // 4. nome
}

function renderFilters(projects) {
  const nav = document.getElementById("filters");
  const groups = new Map();
  let none = 0;
  for (const p of projects) {
    if (!p.label) { none++; continue; }
    const k = key(p);
    const g = groups.get(k) || { text: p.label, count: 0 };
    g.count++;
    groups.set(k, g);
  }
  if (!groups.size) {
    nav.hidden = true;
    nav.replaceChildren();
    filter = "all";
    return;
  }

  const items = [["all", "Tutti", projects.length]];
  if (none) items.push([NONE, "Senza etichetta", none]);
  [...groups].sort(([a], [b]) => a.localeCompare(b, "it"))
  .forEach(([k, g]) => items.push([k, g.text, g.count]));

  if (!items.some(i => i[0] === filter)) filter = "all";

  nav.hidden = false;
  nav.replaceChildren(...items.map(([k, text, count]) => {
    const b = el("button", `filter${k === filter ? " active" : ""}`, `${text} · ${count}`);
    b.type = "button";
    b.addEventListener("click", () => { filter = k; saveFilter(k); render(); });
    return b;
  }));
}

function render() {
  if (!current) return;
  const data = current;

  document.getElementById("title").textContent = data.title;
  document.title = data.title;

  const proxy = document.getElementById("proxy");
  proxy.textContent = data.proxy ? "Proxy attivo" : "Proxy non raggiungibile";
  proxy.className = `chip ${data.proxy ? "online" : "error"}`;

  const err = document.getElementById("error");
  err.hidden = !data.error;
  err.textContent = data.error || "";

  renderFilters(data.projects);

  const shown = data.projects.filter(p => filter === "all" || key(p) === filter).sort(cmp);
  const online = shown.filter(p => p.state === "online").length;
  document.getElementById("summary").textContent = `${online} / ${shown.length} online`;
  document.getElementById("grid").replaceChildren(...shown.map(card));
}

async function refresh() {
  try {
    const res = await fetch("/api/projects", { cache: "no-store" });
    if (!res.ok) throw new Error();
    const data = await res.json();

    const sig = JSON.stringify([data.title, data.proxy, data.error, data.projects.map(p => ({ ...p, ms: null }))]);
    if (sig === last) return;
    last = sig;
    current = data;
    render();
  } catch {
    last = "";
    const err = document.getElementById("error");
    err.hidden = false;
    err.textContent = "Dashboard non raggiungibile.";
  }
}

refresh();
setInterval(() => { if (!document.hidden) refresh(); }, 8000);
document.addEventListener("visibilitychange", () => { if (!document.hidden) refresh(); });
