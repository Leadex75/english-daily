window.EDSearch = (() => {
  function tokens(value) {
    return String(value || '').toLowerCase().match(/[\wÀ-ÿ’'-]+/g) || [];
  }

  function unique(values) {
    return [...new Set(values.filter(Boolean))];
  }

  function weight(entry, token) {
    let score = 0;
    if (String(entry.title || '').toLowerCase().includes(token)) score += 6;
    const history = (entry.history_terms || []).map((item) => (
      typeof item === 'string' ? item : (item.text || item.meaning || '')
    )).join(' ').toLowerCase();
    if (history.includes(token)) score += 4;
    if (String(entry.summary || entry.meaning || entry.meaning_fr || '').toLowerCase().includes(token)) score += 2;
    if (String(entry.body || '').toLowerCase().includes(token)) score += 1;
    if (String(entry.source || '').toLowerCase().includes(token)) score += 1;
    return score;
  }

  function snippet(entry, token) {
    const text = String(entry.body || entry.summary || entry.meaning || '');
    const at = text.toLowerCase().indexOf(token);
    if (!text) return '';
    if (at < 0) return text.slice(0, 160);
    const start = Math.max(0, at - 60);
    return `${start ? '…' : ''}${text.slice(start, at + token.length + 90)}${at + token.length + 90 < text.length ? '…' : ''}`;
  }

  function query(index, term, level = null, limit = 20) {
    const wanted = unique(tokens(term));
    if (!wanted.length || !index || !Array.isArray(index.items)) return [];
    const results = [];
    for (const entry of index.items) {
      if (level && entry.level && entry.level !== level) continue;
      const matched = wanted.filter((token) => weight(entry, token) > 0);
      if (!matched.length) continue;
      const score = matched.reduce((sum, token) => sum + weight(entry, token), 0);
      results.push({
        score,
        matched_terms: matched,
        date: entry.date || '',
        level: entry.level || '',
        category: entry.category || '',
        kind: entry.kind || '',
        title: entry.title || '',
        source: entry.source || '',
        url: entry.url || '',
        guid_hash: entry.guid_hash || '',
        snippet: snippet(entry, matched[0]),
      });
    }
    results.sort((a, b) => b.score - a.score || String(b.date).localeCompare(String(a.date)) || a.title.localeCompare(b.title));
    return results.slice(0, Math.max(1, Math.min(100, Number(limit) || 20)));
  }

  function path(payload) {
    return payload && payload.meta ? payload.meta.search_path : '';
  }

  function merge(indexes) {
    const items = [];
    const seen = new Set();
    for (const index of Array.isArray(indexes) ? indexes : []) {
      for (const entry of (index && Array.isArray(index.items)) ? index.items : []) {
        const key = [entry.date, entry.guid_hash, entry.kind, entry.title].join('|');
        if (seen.has(key)) continue;
        seen.add(key);
        items.push(entry);
      }
    }
    items.sort((a, b) => String(b.date || '').localeCompare(String(a.date || '')));
    return { items };
  }

  return { query, path, merge, tokens };
})();
