window.EDStore = (() => {
  const PREFIX = 'english-daily:';

  function get(key, fallback = null) {
    const raw = localStorage.getItem(key);
    if (raw === null) return fallback;
    try { return JSON.parse(raw); } catch (err) { return raw; }
  }

  function set(key, value) {
    const raw = typeof value === 'string' ? value : JSON.stringify(value);
    localStorage.setItem(key, raw);
  }

  function remove(key) {
    localStorage.removeItem(key);
  }

  function keys(prefix = PREFIX) {
    const result = [];
    for (let i = 0; i < localStorage.length; i += 1) {
      const key = localStorage.key(i);
      if (key && key.startsWith(prefix)) result.push(key);
    }
    return result;
  }

  function clearPrefix(prefix) {
    for (const key of keys(prefix)) remove(key);
  }

  return { PREFIX, get, set, remove, keys, clearPrefix };
})();
