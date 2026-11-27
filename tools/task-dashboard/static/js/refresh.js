// The refresh button: a ring that fills until the next refresh, and spins while a fetch runs.
// A click refreshes now and restarts the count; a slow fetch never overlaps the next one.
// startRefresh returns the refresh, so the caller can run it at once.

export const PERIOD = 30;  // seconds

const R = 14, CIRC = 2 * Math.PI * R;

export function startRefresh(slot, refresh) {
  slot.innerHTML = `<button type="button" class="refresh" aria-label="Refresh now">
      <svg viewBox="0 0 36 36" aria-hidden="true">
        <circle class="track" cx="18" cy="18" r="${R}"></circle>
        <circle class="ring" cx="18" cy="18" r="${R}" stroke-dasharray="${CIRC}" stroke-dashoffset="${CIRC}"></circle>
        <path class="arrow" d="M23.5 13.5a7 7 0 1 0 1.5 4.5M23.5 9.5v4h-4"></path>
      </svg></button><span class="meta" id="next"></span>`;
  const button = slot.querySelector("button"), ring = slot.querySelector(".ring"), next = slot.querySelector("#next");
  let due = 0, busy = false;

  async function run() {
    if (busy) return;
    busy = true;
    button.classList.add("busy");
    next.textContent = "refreshing…";
    try {
      await refresh();
    } finally {
      busy = false;
      button.classList.remove("busy");
      due = Date.now() + PERIOD * 1000;
      tick();
    }
  }

  function tick() {
    if (busy) return;
    const left = Math.max(0, (due - Date.now()) / 1000);
    ring.setAttribute("stroke-dashoffset", String(CIRC * left / PERIOD));
    next.textContent = `next refresh in ${Math.ceil(left)} s`;
    button.title = `Refresh now (next refresh in ${Math.ceil(left)} s)`;
    if (left <= 0) run();
  }

  button.addEventListener("click", run);
  setInterval(tick, 250);
  run();
  return run;  // to refresh at once, e.g. when the page opens another task
}
