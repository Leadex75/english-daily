window.EDSettings = (() => {
  const KEY = `${(window.EDStore && window.EDStore.PREFIX) || 'english-daily:'}settings`;
  const THEMES = ['system', 'paper', 'sepia', 'ink', 'contrast'];
  const TEXT_SIZES = ['small', 'medium', 'large'];
  const FONTS = ['serif', 'sans'];
  const SPEEDS = [0.8, 1, 1.25];
  const DEFAULTS = {
    theme: 'system',
    textSize: 'medium',
    readingFont: 'serif',
    speed: 1,
    showFeedback: true,
    autoMarkRead: true,
    reduceMotion: false,
  };

  function oneOf(value, allowed, fallback) {
    return allowed.includes(value) ? value : fallback;
  }

  function normalize(value) {
    const raw = value && typeof value === 'object' ? value : {};
    const speed = Number(raw.speed);
    return {
      theme: oneOf(raw.theme, THEMES, DEFAULTS.theme),
      textSize: oneOf(raw.textSize, TEXT_SIZES, DEFAULTS.textSize),
      readingFont: oneOf(raw.readingFont, FONTS, DEFAULTS.readingFont),
      speed: SPEEDS.includes(speed) ? speed : DEFAULTS.speed,
      showFeedback: raw.showFeedback === undefined ? DEFAULTS.showFeedback : Boolean(raw.showFeedback),
      autoMarkRead: raw.autoMarkRead === undefined ? DEFAULTS.autoMarkRead : Boolean(raw.autoMarkRead),
      reduceMotion: raw.reduceMotion === undefined ? DEFAULTS.reduceMotion : Boolean(raw.reduceMotion),
    };
  }

  function load(store) {
    const source = store || window.EDStore;
    const value = source && typeof source.get === 'function' ? source.get(KEY, null) : null;
    return normalize(value);
  }

  function save(preferences, store) {
    const target = store || window.EDStore;
    const value = normalize(preferences);
    if (target && typeof target.set === 'function') target.set(KEY, value);
    return value;
  }

  function apply(preferences, root) {
    const value = normalize(preferences);
    const element = root || document.documentElement;
    element.dataset.theme = value.theme;
    element.dataset.textSize = value.textSize;
    element.dataset.readingFont = value.readingFont;
    element.dataset.motion = value.reduceMotion ? 'reduce' : 'auto';
    return value;
  }

  return {
    KEY,
    THEMES,
    TEXT_SIZES,
    FONTS,
    SPEEDS,
    DEFAULTS,
    normalize,
    load,
    save,
    apply,
  };
})();
