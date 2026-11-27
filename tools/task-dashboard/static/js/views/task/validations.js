// Validations tab: every validation folded, pending and failed first; unfolded, its file in full.
import {esc, chip} from "../../format.js";
import {fields, empty} from "./parts.js";

const FIRST = ["pending", "failed"];
const rank = v => FIRST.includes(v.status) ? FIRST.indexOf(v.status) : FIRST.length;
const byNumber = (a, b) => a.id.localeCompare(b.id, undefined, {numeric: true});

function validation(v, L) {
  return `<details class="entry" data-key="${esc(v.id)}"><summary><b>${esc(v.id)}</b> <span>${esc(v.title)}</span> ${chip(v.status)}</summary>
    ${fields(v, [["Where", "where"], ["Depends on", "depends_on"], ["Decides", "decides"], ["How", "how"],
                 ["Expected", "expected"], ["Date", "date"], ["Evidence", "evidence"], ["Attachments", "attachments"],
                 ["File", "file"]], L)}</details>`;
}

export function render(d, L) {
  if (!d.validations.length) return empty("No validations.");
  return [...d.validations].sort((a, b) => rank(a) - rank(b) || byNumber(a, b)).map(v => validation(v, L)).join("");
}
