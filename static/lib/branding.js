window.EDBrand = (() => {
  const ROUTES = ['today', 'archive', 'anki', 'settings'];
  const MONTHS = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December'];
  const WEEKDAYS = ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday'];

  function languageCodes(payload) {
    const languages = payload && Array.isArray(payload.languages) ? payload.languages : [];
    const codes = [];
    for (const entry of languages) {
      const code = String(entry || '').trim();
      if (code && !codes.includes(code)) codes.push(code);
    }
    return codes.length ? codes : ['en'];
  }

  function defaultLanguage(payload) {
    const codes = languageCodes(payload);
    const wanted = String((payload && payload.default) || '').trim();
    if (wanted && codes.includes(wanted)) return wanted;
    return codes.includes('en') ? 'en' : codes[0];
  }

  function normalizeLanguage(value, payload) {
    const codes = languageCodes(payload);
    const wanted = String(value || '').trim();
    if (wanted && codes.includes(wanted)) return wanted;
    return defaultLanguage(payload);
  }

  function languageLabel(payload, lang) {
    const code = String(lang || '').trim();
    const labels = payload && typeof payload.labels === 'object' ? payload.labels : {};
    const metadata = payload && typeof payload.metadata === 'object' ? payload.metadata : {};
    return String(
      labels[code] ||
      (metadata[code] && metadata[code].label) ||
      (code === 'es' ? 'Español' : code === 'en' ? 'English' : code.toUpperCase() || 'English')
    );
  }

  function languageOptions(payload) {
    return languageCodes(payload).map((code) => ({ code, label: languageLabel(payload, code) }));
  }

  function route(value) {
    const raw = String(value || '').replace(/^#\/?/, '').split(/[?&]/)[0];
    return ROUTES.includes(raw) ? raw : 'today';
  }

  function brand(payload, lang) {
    const metadata = payload && typeof payload.metadata === 'object' ? payload.metadata : {};
    const brands = payload && typeof payload.brands === 'object' ? payload.brands : {};
    const raw = String(lang || (payload && payload.default) || 'en').trim();
    const codes = languageCodes(payload);
    const language = codes.includes(raw) ? raw : normalizeLanguage(raw, payload);
    return String(
      (metadata[language] && metadata[language].brand) ||
      brands[language] ||
      (language === 'es' ? 'Spanish Daily' : raw === 'es' ? 'Spanish Daily' : 'English Daily')
    );
  }

  function tagline(payload, lang) {
    const metadata = payload && typeof payload.metadata === 'object' ? payload.metadata : {};
    const taglines = payload && typeof payload.taglines === 'object' ? payload.taglines : {};
    const raw = String(lang || (payload && payload.default) || 'en').trim();
    const codes = languageCodes(payload);
    const language = codes.includes(raw) ? raw : normalizeLanguage(raw, payload);
    return String(
      (metadata[language] && metadata[language].tagline) ||
      taglines[language] ||
      (language === 'es' ? 'Un poco de español, cada día.' : raw === 'es' ? 'Un poco de español, cada día.' : 'A little English, every day.')
    );
  }

  function formatLongDate(value) {
    const parts = String(value || '').split('-');
    if (parts.length !== 3) return '';
    const year = Number(parts[0]);
    const month = Number(parts[1]);
    const day = Number(parts[2]);
    if (!year || month < 1 || month > 12 || day < 1 || day > 31) return '';
    const date = new Date(Date.UTC(year, month - 1, day));
    if (date.getUTCFullYear() !== year || date.getUTCMonth() !== month - 1 || date.getUTCDate() !== day) return '';
    return `${WEEKDAYS[date.getUTCDay()]} ${day} ${MONTHS[month - 1]} ${year}`;
  }

  return {
    languageCodes,
    defaultLanguage,
    normalizeLanguage,
    languageLabel,
    languageOptions,
    route,
    brand,
    tagline,
    formatLongDate,
    routes: ROUTES.slice(),
  };
})();
