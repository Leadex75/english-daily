window.EDAnnotations = (() => {
  const PREFIX = 'eds';

  function keyPrefix(lang, day) {
    return `${PREFIX}.${String(lang || 'en')}.annotations.${String(day || 'today')}.`;
  }

  function storageKey(lang, day, item) {
    return `${keyPrefix(lang, day)}${String(item || 'daily')}`;
  }

  function hash(value) {
    let result = 2166136261;
    const text = String(value || '');
    for (let i = 0; i < text.length; i += 1) {
      result ^= text.charCodeAt(i);
      result = Math.imul(result, 16777619);
    }
    return (result >>> 0).toString(36);
  }

  function noteId(note) {
    const input = note || {};
    return hash(`${input.day || ''}|${input.item || ''}|${input.quote || ''}|${input.text || ''}`);
  }

  function create(input) {
    const note = input || {};
    return {
      id: noteId(note),
      lang: String(note.lang || 'en'),
      day: String(note.day || ''),
      item: String(note.item || ''),
      quote: String(note.quote || ''),
      text: String(note.text || '').trim(),
      saved_at: String(note.saved_at || ''),
    };
  }

  function read(store, key) {
    const value = store && typeof store.get === 'function' ? store.get(key, []) : [];
    return Array.isArray(value) ? value.filter(Boolean) : [];
  }

  function save(note, store) {
    const target = store || window.EDStore;
    const entry = create(note);
    if (!entry.text) return null;
    const key = storageKey(entry.lang, entry.day, entry.item);
    const notes = read(target, key).filter((item) => item.id !== entry.id);
    notes.push(entry);
    if (target && typeof target.set === 'function') target.set(key, notes);
    return entry;
  }

  function list(store, lang, day) {
    const source = store || window.EDStore;
    const prefix = keyPrefix(lang, day);
    const keys = source && typeof source.keys === 'function' ? source.keys(prefix) : [];
    const result = [];
    for (const key of keys) {
      for (const entry of read(source, key)) {
        result.push(create(entry));
      }
    }
    return result.sort((left, right) => `${left.item}|${left.id}`.localeCompare(`${right.item}|${right.id}`));
  }

  function remove(id, store, lang, day) {
    const target = store || window.EDStore;
    const prefix = keyPrefix(lang, day);
    const keys = target && typeof target.keys === 'function' ? target.keys(prefix) : [];
    let removed = 0;
    for (const key of keys) {
      const notes = read(target, key);
      const kept = notes.filter((entry) => create(entry).id !== id);
      removed += notes.length - kept.length;
      if (kept.length !== notes.length) {
        if (target && typeof target.set === 'function') target.set(key, kept);
      }
    }
    return removed;
  }

  function summary(store, lang, day) {
    const notes = list(store, lang, day);
    return { total: notes.length, items: new Set(notes.map((note) => note.item)).size };
  }

  return { PREFIX, keyPrefix, storageKey, hash, noteId, create, save, list, remove, summary };
})();
