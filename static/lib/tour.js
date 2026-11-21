window.EDTour = (() => {
  const STATE_KEY = `${window.EDStore.PREFIX}tour`;

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

  return { steps, state, start, advance, go, end };
})();
