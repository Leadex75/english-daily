window.EDReading = (() => {
  const ATTRIBUTE = 'data-reading';
  const FOCUS = 'focus';
  const OFF = 'off';

  function root(element) {
    return element || (typeof document !== 'undefined' ? document.documentElement : null);
  }

  function normalize(value) {
    return value === FOCUS ? FOCUS : OFF;
  }

  function apply(enabled, element) {
    const target = root(element);
    if (!target || !target.dataset) return OFF;
    const value = normalize(enabled ? FOCUS : OFF);
    target.dataset.reading = value;
    return value;
  }

  function isEnabled(element) {
    const target = root(element);
    return Boolean(target && target.dataset && target.dataset.reading === FOCUS);
  }

  function toggle(element) {
    return apply(!isEnabled(element), element);
  }

  return { ATTRIBUTE, FOCUS, OFF, normalize, apply, isEnabled, toggle };
})();
