// A task's own page: back link, title, step, and one tab at a time, all from /api/tasks/<repo>/<id>.
import {esc} from "../format.js";
import {links, reveal} from "./task/links.js";
import * as summary from "./task/summary.js";
import * as requirements from "./task/requirements.js";
import * as graph from "./task/graph.js";
import * as validations from "./task/validations.js";
import * as decisions from "./task/decisions.js";
import * as features from "./task/features.js";
import * as pending from "./task/pending.js";
import * as journal from "./task/journal.js";
import * as docs from "./task/docs.js";

export const TABS = [
  ["summary", "Summary", summary],
  ["requirements", "Requirements", requirements],
  ["graph", "Graph", graph],
  ["validations", "Validations", validations],
  ["decisions", "Decisions", decisions],
  ["features", "Features", features],
  ["pending", "Pending", pending],
  ["journal", "Journal", journal],
  ["docs", "Docs", docs],
];

// The entries the user unfolded on the open task, in any tab, so a refresh or a tab switch keeps them open.
const unfolded = {task: null, keys: new Set()};

function remember(event) {
  const el = event.target;
  if (el.tagName !== "DETAILS" || !el.dataset.key) return;
  if (el.open) unfolded.keys.add(el.dataset.key);
  else unfolded.keys.delete(el.dataset.key);
}

// A link to the id already in the hash fires no hashchange: show its entry again from here.
function showAgain(event) {
  const link = event.target.closest("a.ref");
  if (!link || link.getAttribute("href") !== location.hash) return;
  const focus = new URLSearchParams(location.hash.slice(1)).get("focus");
  if (focus) reveal(event.currentTarget, focus);
}

// route: {task: "<repo>/<id>", tab, focus}; focus unfolds and shows that entry (only when the hash changed).
export function render(detail, el, route, {focus = false} = {}) {
  if (unfolded.task !== route.task) Object.assign(unfolded, {task: route.task, keys: new Set()});
  if (!el.dataset.listens) {  // once per element; toggle does not bubble, so it is caught in the capture phase
    el.addEventListener("toggle", remember, true);
    el.addEventListener("click", showAgain);
    el.dataset.listens = "1";
  }
  const [name, , view] = TABS.find(([key]) => key === route.tab) || TABS[0];
  const L = links(route.task, detail);
  const row = detail.row;
  el.innerHTML = `<nav class="crumbs"><a href="#">← All tasks</a><span class="id">${esc(row.repo)} / ${esc(row.id)}</span></nav>
    <div class="page-head"><h2 class="page-title">${esc(row.title || row.id)}</h2>
      <span class="chip step" title="${esc(row.step.reason)}">${esc(row.step.step)}</span>
      <span class="sub">${L.text(row.step.reason)}</span></div>
    <nav class="tabs" role="tablist">${TABS.map(([key, label]) =>
      `<a role="tab" href="${L.href(key)}"${key === name ? ` class="on" aria-selected="true"` : ""}>${label}</a>`).join("")}</nav>
    <div class="tab">${view.render(detail, L)}</div>`;
  view.mount?.(el.querySelector(".tab"), detail, L);
  for (const details of el.querySelectorAll("details[data-key]")) {
    if (unfolded.keys.has(details.dataset.key)) details.open = true;
  }
  if (focus && route.focus) reveal(el, route.focus);
}
