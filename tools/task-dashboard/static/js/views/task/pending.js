// Pending tab: every action waiting on someone else, folded, open ones first; unfolded, its refs, closing and link.
import {esc, chip} from "../../format.js";
import {fields, empty} from "./parts.js";

const byNumber = (a, b) => String(a.id).localeCompare(String(b.id), undefined, {numeric: true});

function item(p, L) {
  return `<details class="entry" data-key="${esc(p.id)}"><summary><b>${esc(p.id)}</b>
      <span><b>${esc((p.with || []).join(", "))}</b> · ${esc(p.action)}</span> ${chip(p.status)}</summary>
    ${fields(p, [["Action", "action"], ["Refs", "refs"], ["Opened", "date"], ["Closed", "closed"], ["Link", "link"],
                 ["Comment", "aha_comment"]], L)}</details>`;
}

export function render(d, L) {
  if (!d.pending.length) return empty("No pending items.");
  const open = p => p.status === "open" ? 0 : 1;
  return [...d.pending].sort((a, b) => open(a) - open(b) || byNumber(a, b)).map(p => item(p, L)).join("");
}
