window.EDBrand = (() => {
  const ROUTES = ['today', 'archive', 'glossary', 'settings'];
  const MONTHS = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December'];
  const WEEKDAYS = ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday'];

  function route(value) {
    const raw = String(value || '').replace(/^#\/?/, '').split(/[?&]/)[0];
    return ROUTES.includes(raw) ? raw : 'today';
  }

  function brand(payload, lang) {
    const metadata = payload && typeof payload.metadata === 'object' ? payload.metadata : {};
    const brands = payload && typeof payload.brands === 'object' ? payload.brands : {};
    const language = String(lang || (payload && payload.default) || 'en');
    return String(
      (metadata[language] && metadata[language].brand) ||
      brands[language] ||
      (language === 'es' ? 'Spanish Daily' : 'English Daily')
    );
  }

  function tagline(payload, lang) {
    const metadata = payload && typeof payload.metadata === 'object' ? payload.metadata : {};
    const taglines = payload && typeof payload.taglines === 'object' ? payload.taglines : {};
    const language = String(lang || (payload && payload.default) || 'en');
    return String(
      (metadata[language] && metadata[language].tagline) ||
      taglines[language] ||
      'A little English, every day.'
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

  return { route, brand, tagline, formatLongDate, routes: ROUTES.slice() };
})();
