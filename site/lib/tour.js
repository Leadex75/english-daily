window.EDTour = (() => {
  const STATE_KEY = `${window.EDStore.PREFIX}tour`;
  const SEEN_KEY = `${window.EDStore.PREFIX}tour:seen`;

  function steps(payload) {
    return payload && Array.isArray(payload.tour) ? payload.tour : [];
  }

  function state() {
    return window.EDStore.get(STATE_KEY, { index: 0, open: false });
  }

  function save(index, open) {
    const value = { index, open };
    window.EDStore.set(STATE_KEY, value);
    return value;
  }

  function start(index = 0) {
    return save(index, true);
  }

  function advance(total) {
    const current = state();
    const index = Math.min(total, current.index + 1);
    return save(index, index < total);
  }

  function go(index) {
    return save(Math.max(0, index), true);
  }

  function end() {
    return save(0, false);
  }

  function seen() {
    return Boolean(window.EDStore.get(SEEN_KEY, false));
  }

  function markSeen() {
    window.EDStore.set(SEEN_KEY, true);
    return true;
  }

  return { steps, state, start, advance, go, end, seen, markSeen };
})();
