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
  const meta = [source.enabled ? `every ${minutes(source.every_minutes)}` : "paused", checked].join(" · ");
  const link = el("a", { href: source.target, textContent: source.target, target: "_blank", rel: "noopener" });
  return el("li", {}, el("div", {}, link, el("div", { className: "meta", textContent: meta })), el("div", { className: "actions" }, toggle, remove));
}

// One panel per page-based input kind; site-specific kinds reuse it with their own copy.
export function pageInput({ kind, title, hint, placeholder, empty = "No pages yet." }) {
  return {
  kind,
  title,
  hint,
  mount(container, sources, reload) {
    const url = el("input", { type: "url", required: true, placeholder });
    const every = el("select", { title: "How often to check" }, ...EVERY.map((n) => el("option", { value: n, textContent: `every ${minutes(n)}`, selected: n === 60 })));
    const error = el("p", { className: "error" });
    const form = el("form", { className: "inline" }, url, every, el("button", { type: "submit", textContent: "+ Add page" }));
    form.addEventListener("submit", async (e) => {
      e.preventDefault();
      try {
        await api("/api/sources", { method: "POST", body: { kind, target: url.value.trim(), every_minutes: Number(every.value) } });
        url.value = "";
        reload();
      } catch (err) {
        error.textContent = err.message;
      }
    });
    const list = el("ul", { className: "rows" }, ...sources.map((s) => row(s, reload)));
    if (!sources.length) list.append(el("li", { className: "meta", textContent: empty }));
    container.append(form, error, list);
  },
  };
}

export default pageInput({
  kind: "web",
  title: "Web",
  hint: "dash checks each page on its schedule. When the visible text changes, hermes gets the new text as a memory.",
  placeholder: "https://example.com/changelog",
});
