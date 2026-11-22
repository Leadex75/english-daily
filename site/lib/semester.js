window.EDSemester = (() => {
  const PREFIX = 'eds';
  const DAY_MS = 86400000;

  function storageKey(lang) {
    return `${PREFIX}.${String(lang || 'en')}.semester`;
  }

  function validDay(value) {
    const parts = String(value || '').split('-');
    if (parts.length !== 3) return '';
    const year = Number(parts[0]);
    const month = Number(parts[1]);
    const date = Number(parts[2]);
    if (!year || month < 1 || month > 12 || date < 1 || date > 31) return '';
    const parsed = new Date(Date.UTC(year, month - 1, date));
    if (parsed.getUTCFullYear() !== year || parsed.getUTCMonth() !== month - 1 || parsed.getUTCDate() !== date) return '';
    return parsed.toISOString().slice(0, 10);
  }

  function addDays(day, count) {
    const valid = validDay(day);
    if (!valid) return '';
    const next = new Date(`${valid}T00:00:00Z`);
    next.setUTCDate(next.getUTCDate() + Number(count));
    return next.toISOString().slice(0, 10);
  }

  function dayNumber(day) {
    const valid = validDay(day);
    return valid ? Math.floor(Date.parse(`${valid}T00:00:00Z`) / DAY_MS) : NaN;
  }

  function normalize(value) {
    const input = value && typeof value === 'object' ? value : {};
    const start = validDay(input.start) || validDay(input.semesterStart) || '';
    const end = validDay(input.end) || validDay(input.semesterEnd) || start;
    const weeklyGoal = Math.max(1, Number(input.weeklyGoal || input.goalPerWeek) || 5);
    return { start, end: end && start && end < start ? start : end, weeklyGoal };
  }

  function weeks(value) {
    const config = normalize(value);
    if (!config.start || !config.end) return [];
    const startNumber = dayNumber(config.start);
    const endNumber = dayNumber(config.end);
    const result = [];
    let cursor = startNumber;
    let index = 1;
    while (cursor <= endNumber && result.length < 60) {
      const finish = Math.min(cursor + 6, endNumber);
      result.push({
        index,
        start: addDays(config.start, (cursor - startNumber)),
        end: addDays(config.start, (finish - startNumber)),
        count: 0,
      });
      cursor = finish + 1;
      index += 1;
    }
    return result;
  }

  function practicedDays(entries) {
    const result = [];
    for (const entry of Array.isArray(entries) ? entries : []) {
      const day = validDay(entry && typeof entry === 'object' ? entry.date : entry);
      if (day) result.push(day);
    }
    return [...new Set(result)].sort();
  }

  function progress(entries, value) {
    const config = normalize(value);
    const days = practicedDays(entries);
    const windows = weeks(config).map((week) => ({ ...week, days: [] }));
    for (const day of days) {
      const number = dayNumber(day);
      for (const week of windows) {
        if (number >= dayNumber(week.start) && number <= dayNumber(week.end)) week.days.push(day);
      }
    }
    for (const week of windows) week.count = week.days.length;
    const completed = days.filter((day) => {
      const number = dayNumber(day);
      return number >= dayNumber(config.start) && number <= dayNumber(config.end);
    }).length;
    const goal = config.weeklyGoal * windows.length;
    return {
      ...config,
      days,
      completed,
      goal,
      percent: goal ? Math.min(100, Math.round((completed / goal) * 100)) : 0,
      weeks: windows,
    };
  }

  function load(lang, store) {
    const source = store || window.EDStore;
    if (!source || typeof source.get !== 'function') return normalize(null);
    return normalize(source.get(storageKey(lang), null));
  }

  function save(lang, value, store, timestamp) {
    const target = store || window.EDStore;
    const payload = normalize(value);
    if (timestamp) payload.saved_at = String(timestamp);
    if (target && typeof target.set === 'function') target.set(storageKey(lang), payload);
    return payload;
  }

  return {
    PREFIX,
    DAY_MS,
    storageKey,
    validDay,
    addDays,
    dayNumber,
    normalize,
    weeks,
    practicedDays,
    progress,
    load,
    save,
  };
})();
