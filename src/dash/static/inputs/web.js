import { api, el, minutes } from "../lib.js";

const EVERY = [15, 60, 360, 1440, 10080];

function row(source, reload) {
  const toggle = el("button", { textContent: source.enabled ? "Pause" : "Resume" });
  toggle.addEventListener("click", async () => {
    await api(`/api/sources/${source.id}`, { method: "PATCH", body: { enabled: !source.enabled } });
    reload();
  });
  const remove = el("button", { textContent: "Remove" });
  remove.addEventListener("click", async () => {
    if (!confirm(`Stop watching ${source.target}?`)) return;
    await api(`/api/sources/${source.id}`, { method: "DELETE" });
    reload();
  });
  const checked = source.checked_at ? `checked ${source.checked_at.slice(0, 16).replace("T", " ")}` : "not checked yet";
  const meta = [pageInput.labelOf(source.kind), source.enabled ? `every ${minutes(source.every_minutes)}` : "paused", checked].join(" · ");
  const link = el("a", { href: source.target, textContent: source.target, target: "_blank", rel: "noopener" });
  return el("li", {}, el("div", {}, link, el("div", { className: "meta", textContent: meta })), el("div", { className: "actions" }, toggle, remove));
}

// Sites with their own parser; any other URL is a plain `web` page.
const HOSTS = {
  "news.ycombinator.com": { kind: "hackernews", label: "Hacker News" },
  "bushwickdaily.com": { kind: "bushwick", label: "Bushwick Daily" },
};
const ATOM = { kind: "atom", label: "Atom feed" };
const WEB = { kind: "web", label: "page" };

export const pageInput = {
  kinds: ["web", ATOM.kind, ...Object.values(HOSTS).map((h) => h.kind)],

  // The input source for a URL: ".atom" paths are feeds, then picked by host name ("www." ignored).
  fromUrl(url) {
    const { hostname, pathname } = new URL(url);
    if (pathname.endsWith(".atom")) return ATOM;
    return HOSTS[hostname.replace(/^www\./, "")] || WEB;
  },

  labelOf(kind) {
    return ([ATOM, ...Object.values(HOSTS)].find((h) => h.kind === kind) || WEB).label;
  },
};

export default {
  kind: "web",
  kinds: pageInput.kinds,
  title: "Web",
  hint: "dash checks each page on its schedule. Atom feeds (URLs ending in .atom, like a GitHub commits feed) and Hacker News and Bushwick Daily pages become one memory per new entry; any other page becomes a memory when its visible text changes.",
  mount(container, sources, reload) {
    const url = el("input", { type: "url", required: true, placeholder: "https://news.ycombinator.com/" });
    const every = el("select", { title: "How often to check" }, ...EVERY.map((n) => el("option", { value: n, textContent: `every ${minutes(n)}`, selected: n === 60 })));
    const error = el("p", { className: "error" });
    const form = el("form", { className: "inline" }, url, every, el("button", { type: "submit", textContent: "+ Add page" }));
    form.addEventListener("submit", async (e) => {
      e.preventDefault();
      try {
        const target = url.value.trim();
        const { kind } = pageInput.fromUrl(target);
        await api("/api/sources", { method: "POST", body: { kind, target, every_minutes: Number(every.value) } });
        url.value = "";
        reload();
      } catch (err) {
        error.textContent = err.message;
      }
    });
    const list = el("ul", { className: "rows" }, ...sources.map((s) => row(s, reload)));
    if (!sources.length) list.append(el("li", { className: "meta", textContent: "No pages yet." }));
    container.append(form, error, list);
  },
};
