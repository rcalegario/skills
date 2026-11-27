// The step filter of the Tasks view: a chain of status chips in the order of the /task state machine.
// A chip on shows its tasks; a chip off turns grey and hides them. The hidden set lives here, outside the DOM,
// so the 30 s redraw keeps it, and in localStorage, so a reload keeps it. What is stored is what is hidden, so a
// step seen for the first time shows; with nothing stored, done and legacy start hidden.
import {esc, stepClass} from "../format.js";

// The main line of the chain; spike is a detour from plan to build, drawn above that arrow.
const LINE = ["decide", "consolidate", "plan", "build", "review", "pr", "finish", "done"];
const DETOUR = {from: "plan", via: "spike"};
// Rows without a step, after a divider.
const EXTRA = ["legacy", "error"];

const STORE = "task-dashboard.hidden";
const DEFAULT_HIDDEN = ["done", "legacy"];

// Storage may be missing or throw (private window, blocked site data): then the default holds for the session.
function load() {
  try {
    const saved = JSON.parse(localStorage.getItem(STORE));
    if (Array.isArray(saved)) return new Set(saved.map(String));
  } catch { /* fall back to the default */ }
  return new Set(DEFAULT_HIDDEN);
}

function save() {
  try {
    localStorage.setItem(STORE, JSON.stringify([...hidden]));
  } catch { /* the choice lasts for this session only */ }
}

const hidden = load();

// The chip a task counts under: its step, or legacy, or error.
export const keyOf = t => t.legacy ? "legacy" : t.error || !t.step ? "error" : t.step.step;

export const shown = t => !hidden.has(keyOf(t));

export function toggle(key) {
  if (hidden.has(key)) hidden.delete(key);
  else hidden.add(key);
  save();
}

function filterChip(key, counts) {
  const on = !hidden.has(key);
  return `<button type="button" class="${stepClass(key)}" data-step="${esc(key)}" aria-pressed="${on}"
    title="${on ? "shown: click to hide" : "hidden: click to show"}">${esc(key)} <b class="n">${counts.get(key) || 0}</b></button>`;
}

const arrow = `<span class="arrow" aria-hidden="true">→</span>`;

// The chain with every step (empty ones too), then legacy, error and any step this page does not know.
export function chain(tasks) {
  const counts = new Map();
  for (const t of tasks) counts.set(keyOf(t), (counts.get(keyOf(t)) || 0) + 1);
  const known = new Set([...LINE, DETOUR.via, ...EXTRA]);
  const others = [...counts.keys()].filter(k => !known.has(k)).sort();
  const line = LINE.map((step, i) => {
    const link = i === LINE.length - 1 ? ""
      : step === DETOUR.from
        ? `<span class="detour"><span class="via">${filterChip(DETOUR.via, counts)}</span>${arrow}</span>`
        : arrow;
    return filterChip(step, counts) + link;
  }).join("");
  return `<div class="filter" role="group" aria-label="Filter by step">
    <div class="chain">${line}<span class="divider" aria-hidden="true"></span>
      ${[...EXTRA, ...others].map(k => filterChip(k, counts)).join("")}</div>
    <div class="sub">↺ decide can reopen from any step</div>
  </div>`;
}
