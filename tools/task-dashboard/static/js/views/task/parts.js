// Pieces the tabs share: a labelled list of a YAML entry's fields, lists of ids, journal notes, empty states.
import {esc} from "../../format.js";

const isEmpty = v => v === undefined || v === null || v === "" || (Array.isArray(v) && !v.length);

// A value as text with its ids linked: a list reads one entry per line, a mapping as key: value.
export function value(v, L, feature) {
  if (Array.isArray(v)) {
    return `<ul class="plain">${v.map(x => `<li>${value(x, L, feature)}</li>`).join("")}</ul>`;
  }
  if (v && typeof v === "object") {
    return Object.entries(v).map(([k, x]) => `<div><span class="k">${esc(k)}:</span> ${value(x, L, feature)}</div>`).join("");
  }
  return `<span class="prose">${L.text(v, feature)}</span>`;
}

// The given fields of an entry, in that order, skipping empty ones: [[label, key], ...].
export function fields(entry, pairs, L, feature) {
  const rows = pairs.filter(([, key]) => !isEmpty(entry[key]))
    .map(([label, key]) => `<dt>${esc(label)}</dt><dd>${value(entry[key], L, feature)}</dd>`);
  return rows.length ? `<dl class="fields">${rows.join("")}</dl>` : "";
}

// Ids as links, comma-separated.
export const ids = (list, L, feature) => (list || []).map(id => L.ref(id, feature)).join(", ");

export const empty = text => `<p class="empty">${esc(text)}</p>`;

// A journal note: id, date, type, text and refs.
export function note(n, L) {
  return `<li class="note-entry" data-key="${esc(n.id)}"><span class="when">${esc(n.id)} · ${esc(n.date)}${n.type ? ` · ${esc(n.type)}` : ""}</span>
    <div class="prose">${L.text(n.text)}</div>${n.refs?.length ? `<div class="sub">refs ${ids(n.refs, L)}</div>` : ""}</li>`;
}

export const section = (title, body) => `<section class="block"><h3>${esc(title)}</h3>${body}</section>`;
