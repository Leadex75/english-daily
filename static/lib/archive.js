window.EDArchive = (() => {
  const MONTHS = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December'];
  const WEEKDAYS = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];
  const WEEKDAYS_LONG = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday'];

  function pad(value) {
    return String(value).padStart(2, '0');
  }

  function validDay(value) {
    return /^\d{4}-\d{2}-\d{2}$/.test(String(value || ''));
  }

  function monthKey(value) {
    const text = String(value || '');
    return /^\d{4}-\d{2}/.test(text) ? text.slice(0, 7) : '';
  }

  function shiftMonth(key, delta) {
    const match = /^(\d{4})-(\d{2})$/.exec(String(key || ''));
    if (!match) return '';
    const date = new Date(Date.UTC(Number(match[1]), Number(match[2]) - 1 + Number(delta), 1));
    return `${date.getUTCFullYear()}-${pad(date.getUTCMonth() + 1)}`;
  }

  function months(days) {
    return [...new Set((Array.isArray(days) ? days : []).map(monthKey).filter(Boolean))].sort();
  }

  function label(key) {
    const match = /^(\d{4})-(\d{2})$/.exec(String(key || ''));
    if (!match) return 'Archive';
    const month = Number(match[2]) - 1;
    if (month < 0 || month > 11) return 'Archive';
    return `${MONTHS[month]} ${match[1]}`;
  }

  function buildMonth(key, days, selected, today) {
    const match = /^(\d{4})-(\d{2})$/.exec(String(key || ''));
    const available = new Set((Array.isArray(days) ? days : []).filter(validDay));
    if (!match) {
      return { key: '', label: 'Archive', weekdays: WEEKDAYS, cells: [], availableCount: 0 };
    }
    const year = Number(match[1]);
    const month = Number(match[2]) - 1;
    if (month < 0 || month > 11) {
      return { key, label: 'Archive', weekdays: WEEKDAYS, cells: [], availableCount: 0 };
    }
    const firstWeekday = (new Date(Date.UTC(year, month, 1)).getUTCDay() + 6) % 7;
    const dayCount = new Date(Date.UTC(year, month + 1, 0)).getUTCDate();
    const cells = [];
    for (let index = 0; index < firstWeekday; index += 1) {
      cells.push({ date: '', day: '', available: false, selected: false, today: false, ariaLabel: '' });
    }
    let availableCount = 0;
    for (let day = 1; day <= dayCount; day += 1) {
      const date = `${year}-${pad(month + 1)}-${pad(day)}`;
      const hasEdition = available.has(date);
      if (hasEdition) availableCount += 1;
      const weekday = (new Date(Date.UTC(year, month, day)).getUTCDay() + 6) % 7;
      const notes = [
        hasEdition ? 'edition available' : 'no edition',
        date === today ? 'today' : '',
        date === selected ? 'selected' : '',
      ].filter(Boolean).join(', ');
      cells.push({
        date,
        day,
        available: hasEdition,
        selected: date === selected,
        today: date === today,
        ariaLabel: `${WEEKDAYS_LONG[weekday]} ${day} ${MONTHS[month]} ${year}, ${notes}`,
      });
    }
    while (cells.length % 7 !== 0) {
      cells.push({ date: '', day: '', available: false, selected: false, today: false, ariaLabel: '' });
    }
    return { key, label: label(key), weekdays: WEEKDAYS, cells, availableCount };
  }

  function recentDates(days, count) {
    const sorted = (Array.isArray(days) ? days : []).filter(validDay).slice().sort().reverse();
    return sorted.slice(0, Math.max(1, Math.min(60, Number(count) || 7)));
  }

  return { MONTHS, WEEKDAYS, monthKey, shiftMonth, months, label, buildMonth, recentDates, validDay };
})();
