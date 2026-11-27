// Tasks view: every task in one list, one aligned row each (repo | title / id | reason | step | items | activity);
// a row opens the task's page.
import {esc, bar, ago, sortTasks} from "../format.js";
import {taskHref} from "./task/links.js";
import * as filter from "./filter.js";

// The main repo (the task's folder under tasks/), shown before the step on every row.
const repoChip = t => `<span class="chip repo" title="main repo: ${esc(t.repo)}">${esc(t.repo)}</span>`;

// The step name after a dot in its step's color, the same color as that step's chip in the filter.
const stepCell = step => `<span class="c-step step-${esc(step)}"><span class="dot"></span>${esc(step)}</span>`;

// The reason cell: a slot for the "!" (kept empty when the next action is not the user's, so every reason starts
// at the same x), then the summarized reason with status.py's full text, or the failures, on hover.
// reason is the row's {text, hover, failed} from the server.
const reasonCell = ({text, hover, failed}, mine = false) =>
  `<span class="c-reason${failed ? " err" : ""}">${mine ? `<span class="flag" title="your turn">!</span>`
    : `<span class="flag off"></span>`}<span class="ell" title="${esc(hover)}">${esc(text)}</span></span>`;

// Legacy and broken tasks sit on the same grid with their folder id as the title; they show no progress nor activity.
function unreadable(t) {
  const step = t.legacy ? "legacy" : "error", error = t.legacy ? "" : String(t.error ?? "");
  return `<li class="task ${step}">
    <span class="c-repo">${repoChip(t)}</span>
    <span class="c-main"><span class="title ell" title="${esc(t.id)}">${esc(t.id)}</span>
      <span class="idline">${repoChip(t)}</span></span>
    ${reasonCell({text: error, hover: error, failed: !!error})}
    ${stepCell(step)}<span class="c-prog"></span><span class="c-ago"></span>
  </li>`;
}

function row(t) {
  if (t.legacy || t.error) return unreadable(t);
  const items = t.items, done = items.by_status.concluded || 0;
  const title = t.title || t.id;
  const href = taskHref(`${t.repo}/${t.id}`);
  return `<li class="task link" data-href="${esc(href)}">
    <span class="c-repo">${repoChip(t)}</span>
    <span class="c-main">
      <a class="open title ell" href="${esc(href)}" title="${esc(title)}">${esc(title)}</a>
      <span class="idline">${repoChip(t)}<span class="fid ell" title="${esc(t.id)}">${esc(t.id)}</span></span>
    </span>
    ${reasonCell(t.reason, !!t.step.your_turn)}
    ${stepCell(t.step.step)}
    <span class="c-prog" title="${esc(Object.entries(items.by_status).map(([s, n]) => `${n} ${s}`).join(", "))}">
      ${bar(items.by_status)}<span><b>${done}/${items.total}</b> items</span></span>
    <span class="c-ago" title="${esc(t.last_activity)}">${esc(ago(t.last_activity))}</span>
  </li>`;
}

// onChange tells the page to redraw after a chip is toggled.
let changed = () => {};
export const onChange = fn => { changed = fn; };

// One listener per view element: a click on a chip toggles its step and redraws; a click anywhere on a readable
// row opens its task (the title link handles its own clicks, Tab and Enter).
function bind(el) {
  if (el.dataset.filterBound) return;
  el.dataset.filterBound = "1";
  el.addEventListener("click", event => {
    const task = event.target.closest("li.task.link[data-href]");
    if (task && el.contains(task) && !event.target.closest("a")) {
      location.hash = task.dataset.href;
      return;
    }
    const button = event.target.closest("button[data-step]");
    if (!button || !el.contains(button)) return;
    button.focus();  // a click does not focus a button in every browser; render() keeps the focus on it
    filter.toggle(button.dataset.step);
    changed();
  });
}

// The step of the filter chip that has the focus, so a redraw (a toggle or the 30 s refresh) can give it back.
function focusedStep(el) {
  const active = globalThis.document?.activeElement;
  return active && el.contains(active) ? active.dataset?.step : undefined;
}

// Draws the filter and the tasks it lets through; returns how many are shown.
export function render(data, el) {
  const focused = focusedStep(el);
  if (!data.tasks.length) {
    el.innerHTML = `<p class="empty">No tasks under ${esc(data.home)}/tasks.</p>`;
    return 0;
  }
  bind(el);
  const tasks = sortTasks(data.tasks).filter(filter.shown);
  el.innerHTML = filter.chain(data.tasks) + (tasks.length
    ? `<ul class="list">${tasks.map(row).join("")}</ul>`
    : `<p class="empty">No task matches the filter.</p>`);
  if (focused) el.querySelector(`button[data-step="${CSS.escape(focused)}"]`)?.focus({preventScroll: true});
  return tasks.length;
}
