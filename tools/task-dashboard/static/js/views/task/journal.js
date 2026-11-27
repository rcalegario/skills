// Journal tab: every note as a timeline, newest first.
import {empty, note} from "./parts.js";

export function render(d, L) {
  if (!d.journal.length) return empty("No journal notes.");
  return `<ul class="list timeline">${[...d.journal].reverse().map(n => note(n, L)).join("")}</ul>`;
}
