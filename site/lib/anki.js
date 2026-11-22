(function () {
  const PREFIX = (window.EDStore && window.EDStore.PREFIX) || 'english-daily:';
  const NOTES_KEY = `${PREFIX}anki-notes`;
  const FIELDS = ['Front', 'Back', 'Example', 'Source', 'Level', 'Language', 'Date', 'Guid'];
  const MODEL_NAME = 'English Daily Phrase';
  const DECK_NAME = 'English Daily';
  const FNV_SEEDS = [2166136261, 2654435761, 2246822519, 3266489917];

  function escapeField(value) {
    return String(value == null ? '' : value)
      .replace(/\r\n/g, '<br>')
      .replace(/\n/g, '<br>')
      .replace(/\t/g, ' ')
      .trim();
  }

  function htmlEscape(value) {
    const text = String(value == null ? '' : value).replace(/<br\s*\/?>/gi, '\n');
    return text.split(/\r?\n/).map(function (line) {
      return String(line)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#x27;');
    }).join('<br>');
  }

  function encodeText(value) {
    if (typeof TextEncoder !== 'undefined') return new TextEncoder().encode(value);
    const raw = unescape(encodeURIComponent(value));
    const bytes = new Uint8Array(raw.length);
    for (let index = 0; index < raw.length; index += 1) bytes[index] = raw.charCodeAt(index) & 0xff;
    return bytes;
  }

  function fnv32(text, seed) {
    let hash = seed >>> 0;
    const bytes = encodeText(text);
    for (let index = 0; index < bytes.length; index += 1) {
      hash ^= bytes[index];
      hash = Math.imul(hash, 16777619) >>> 0;
    }
    return hash >>> 0;
  }

  function stableGuid(value) {
    const text = String(value || '');
    return FNV_SEEDS.map(function (seed) {
      return fnv32(text, seed).toString(16).padStart(8, '0');
    }).join('');
  }

  function uniqueSorted(values) {
    return [...new Set(values.filter(Boolean))].sort();
  }

  function buildNote(entry, options) {
    const source = entry || {};
    const opts = options || {};
    const lang = opts.lang || 'en';
    const day = opts.day || '';
    const front = String(source.text || source.expression || '').trim();
    const meaningFr = String(source.meaning_fr || '').trim();
    const meaning = String(source.meaning || '').trim();
    const back = [meaningFr, meaning].filter(Boolean).join(' — ');
    const example = String(source.example || '').trim();
    const key = String(source.key || source.guid_hash || '').trim();
    const noteDate = String(day || source.learned_at || '').trim();
    const kind = String(source.type || source.kind || 'phrase').trim();
    const level = String(source.level || '').trim();
    const ankiSource = String(source.source || 'English Daily').trim();
    const guid = stableGuid([lang, key, front, back, example].join('|'));
    const tags = ['english-daily', `lang-${lang}`, `kind-${kind}`];
    if (noteDate) tags.push(`date-${noteDate}`);
    if (level) tags.push(`level-${level.toLowerCase()}`);
    return {
      guid,
      note_id: parseInt(guid.slice(0, 12), 16),
      model_name: MODEL_NAME,
      deck_name: opts.deckName || DECK_NAME,
      key,
      fields: {
        Front: htmlEscape(front),
        Back: htmlEscape(back),
        Example: htmlEscape(example),
        Source: htmlEscape(ankiSource),
        Level: htmlEscape(level),
        Language: htmlEscape(lang),
        Date: htmlEscape(noteDate),
        Guid: guid,
      },
      tags: uniqueSorted(tags),
    };
  }

  function buildNotes(entries, options) {
    const unique = {};
    for (const entry of Array.isArray(entries) ? entries : []) {
      const note = buildNote(entry, options);
      if (note.fields.Front) unique[note.guid] = note;
    }
    return Object.keys(unique).sort().map(function (guid) { return unique[guid]; });
  }

  function toTsv(cards) {
    return cards.map(function (card) {
      return escapeField(card.front) + '\t' + escapeField(card.back);
    }).join('\n');
  }

  function download(cards, filename) {
    if (!cards || !cards.length) return;
    const text = '\ufeff#separator:tab\n#html:true\n' + toTsv(cards) + '\n';
    const blob = new Blob([text], { type: 'text/plain;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = filename || 'english-daily-anki.txt';
    document.body.appendChild(link);
    link.click();
    link.remove();
    setTimeout(function () { URL.revokeObjectURL(url); }, 1000);
  }

  function copy(cards) {
    if (!navigator.clipboard || !cards || !cards.length) return Promise.resolve(false);
    return navigator.clipboard.writeText(toTsv(cards)).then(function () { return true; }, function () { return false; });
  }

  function available() {
    return Boolean(window.AnkiExport && typeof window.AnkiExport.download === 'function');
  }

  function select(items, isLearned, toCard) {
    return (Array.isArray(items) ? items : []).filter(function (item) {
      return typeof isLearned !== 'function' || isLearned(item);
    }).map(function (item) {
      return typeof toCard === 'function' ? toCard(item) : item;
    }).filter(Boolean);
  }

  function status(item, isLearned, isAvailable) {
    if (!isAvailable) return 'Anki export unavailable offline';
    if (typeof isLearned === 'function' && !isLearned(item)) return 'Mark learned before exporting to Anki';
    return 'Ready for Anki';
  }

  function ankiConnectNote(note, deckName) {
    const deck = deckName || (note && note.deck_name) || DECK_NAME;
    return {
      deckName: deck,
      modelName: (note && note.model_name) || MODEL_NAME,
      fields: Object.assign({}, (note && note.fields) || {}),
      tags: ((note && note.tags) || []).slice(),
      options: {
        allowDuplicate: false,
        duplicateScope: 'deck',
        duplicateScopeOptions: {
          deckName: deck,
          checkChildren: false,
          checkAllModels: false,
        },
      },
    };
  }

  function connect(url, fetchImpl) {
    const endpoint = String(url || 'http://127.0.0.1:8765').replace(/\/+$/, '');
    const send = fetchImpl || (typeof window.fetch === 'function' ? window.fetch.bind(window) : null);
    function invoke(action, params) {
      if (!send) return Promise.reject(new Error('Network fetch is unavailable'));
      return send(endpoint, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ action, version: 6, params: params || {} }),
      }).then(function (response) {
        if (!response.ok) throw new Error(`AnkiConnect returned HTTP ${response.status}`);
        return response.json();
      }).then(function (payload) {
        if (payload && payload.error) throw new Error(String(payload.error));
        return payload ? payload.result : null;
      });
    }
    return {
      url: endpoint,
      invoke,
      check: function () {
        return invoke('version').then(function (version) {
          if (Number(version) < 6) throw new Error('AnkiConnect version 6 or newer is required');
          return Number(version);
        });
      },
      addNotes: function (notes) {
        return invoke('addNotes', { notes: (notes || []).map(function (note) { return ankiConnectNote(note); }) });
      },
    };
  }

  function loadLedger(store) {
    const source = store || window.EDStore;
    const value = source && typeof source.get === 'function' ? source.get(NOTES_KEY, {}) : {};
    return value && typeof value === 'object' && !Array.isArray(value) ? value : {};
  }

  function exportStatus(note, store) {
    const ledger = loadLedger(store);
    return note && note.guid ? ledger[note.guid] || null : null;
  }

  function recordExport(notes, store, result) {
    const target = store || window.EDStore;
    const ledger = loadLedger(target);
    const added = Array.isArray(result) ? result.filter(Boolean).length : 0;
    for (const note of notes || []) {
      ledger[note.guid] = {
        guid: note.guid,
        key: note.key,
        model_name: note.model_name,
        deck_name: note.deck_name,
        exported_at: new Date().toISOString(),
        added,
      };
    }
    if (target && typeof target.set === 'function') target.set(NOTES_KEY, ledger);
    return ledger;
  }

  window.AnkiConnect = connect;
  window.AnkiExport = {
    toTsv,
    download,
    copy,
    available,
    select,
    status,
    buildNote,
    buildNotes,
    ankiConnectNote,
    connect,
    loadLedger,
    exportStatus,
    recordExport,
    stableGuid,
    NOTES_KEY,
    FIELDS,
    MODEL_NAME,
    DECK_NAME,
  };
}());
