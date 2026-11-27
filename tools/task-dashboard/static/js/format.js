// Formatting shared by the views: escaping, progress bars, times, ordering.

export const esc = s => String(s ?? "").replace(/[&<>"']/g,
  c => ({"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"}[c]));

// Requirement and item statuses, from least to most done (the task skill's format.md, Status).
export const STATUSES = ["discovery", "deciding", "decided", "built", "concluded", "dropped"];

export const color = status => STATUSES.includes(status) ? `var(--s-${status})` : "var(--muted)";

export const sum = counts => Object.values(counts).reduce((a, b) => a + b, 0);

// A task's last activity as a sortable string; legacy and error rows have none.
const activity = t => String(t.last_activity ?? "");

// A stacked bar of counts by status, in STATUSES order.
export function bar(byStatus) {
  const total = sum(byStatus);
  if (!total) return `<div class="bar"></div>`;
  const parts = Object.keys(byStatus).sort((a, b) => STATUSES.indexOf(a) - STATUSES.indexOf(b))
    .map(s => `<span style="width:${100 * byStatus[s] / total}%;background:${color(s)}" title="${byStatus[s]} ${esc(s)}"></span>`);
  return `<div class="bar">${parts.join("")}</div>`;
}

// "now", "5 min", "3 h", "2 d" since an ISO local time, short enough for the row's last column.
export function ago(iso, now = new Date()) {
  if (!iso) return "";
  const s = Math.max(0, (now - new Date(iso)) / 1000);
  if (s < 60) return "now";
  if (s < 3600) return `${Math.floor(s / 60)} min`;
  if (s < 86400) return `${Math.floor(s / 3600)} h`;
  return `${Math.floor(s / 86400)} d`;
}

// How a status reads: done, in progress, wrong, or out of play. Requirement statuses keep their own colors.
const TONES = {
  good: ["decided", "passed", "done", "concluded", "chosen", "pass", "fixed", "closed"],
  busy: ["open", "proposed", "pending", "deciding", "doing", "verifying", "building", "review", "recommended",
         "approved", "draft", "todo", "built", "discovery"],
  bad: ["failed", "fail", "must-fix"],
};
export function chip(status) {
  if (status === undefined || status === null || status === "") return "";
  const tone = Object.keys(TONES).find(t => TONES[t].includes(status)) || "off";
  const style = STATUSES.includes(status) ? ` style="border-color:${color(status)}"` : "";
  return `<span class="chip t-${tone}"${style}>${esc(status)}</span>`;
}

// The classes of a chip in a /task step's color (style.css, step-<name>): a row's step chip and its filter chip.
export const stepClass = step => `chip st step-${esc(step)}`;

export const clock = (date = new Date()) => date.toTimeString().slice(0, 8);

// Every task in one list: readable ones by last activity (newest first), then errors, then legacy; ties by id.
export function sortTasks(tasks) {
  const rank = t => t.legacy ? 2 : t.error ? 1 : 0;
  return [...tasks].sort((a, b) => rank(a) - rank(b)
    || activity(b).localeCompare(activity(a)) || a.id.localeCompare(b.id));
}
