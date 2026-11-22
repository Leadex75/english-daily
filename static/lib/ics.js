window.EDICS = (() => {
  const DEFAULT_TIME = '07:00';
  const MINUTES = 15;

  function pad(value) {
    return String(value).padStart(2, '0');
  }

  function dayParts(day) {
    const parts = String(day || '').split('-');
    if (parts.length !== 3) return null;
    const year = Number(parts[0]);
    const month = Number(parts[1]);
    const date = Number(parts[2]);
    if (!year || month < 1 || month > 12 || date < 1 || date > 31) return null;
    const parsed = new Date(Date.UTC(year, month - 1, date));
    if (parsed.getUTCFullYear() !== year || parsed.getUTCMonth() !== month - 1 || parsed.getUTCDate() !== date) return null;
    return { year, month, date };
  }

  function timeParts(value) {
    const parts = String(value || DEFAULT_TIME).split(':');
    if (parts.length !== 2) return { hour: 7, minute: 0 };
    const hour = Number(parts[0]);
    const minute = Number(parts[1]);
    if (!Number.isInteger(hour) || !Number.isInteger(minute) || hour < 0 || hour > 23 || minute < 0 || minute > 59) {
      return { hour: 7, minute: 0 };
    }
    return { hour, minute };
  }

  function stamp(day, value) {
    const date = dayParts(day);
    const time = timeParts(value);
    if (!date) return '';
    return `${date.year}${pad(date.month)}${pad(date.date)}T${pad(time.hour)}${pad(time.minute)}00Z`;
  }

  function escape(value) {
    return String(value == null ? '' : value)
      .replace(/\\/g, '\\\\')
      .replace(/;/g, '\\;')
      .replace(/,/g, '\\,')
      .replace(/\r?\n/g, '\\n');
  }

  function fold(line) {
    const raw = String(line);
    if (raw.length <= 72) return raw;
    const chunks = [raw.slice(0, 72)];
    let rest = raw.slice(72);
    while (rest.length > 71) {
      chunks.push(` ${rest.slice(0, 71)}`);
      rest = rest.slice(71);
    }
    if (rest) chunks.push(` ${rest}`);
    return chunks.join('\r\n');
  }

  function buildEvent(options) {
    const input = options || {};
    const start = stamp(input.day, input.time);
    if (!start) return '';
    const end = new Date(`${start.slice(0, 4)}-${start.slice(4, 6)}-${start.slice(6, 8)}T${start.slice(9, 11)}:${start.slice(11, 13)}:00Z`);
    end.setUTCMinutes(end.getUTCMinutes() + MINUTES);
    const finish = `${end.getUTCFullYear()}${pad(end.getUTCMonth() + 1)}${pad(end.getUTCDate())}T${pad(end.getUTCHours())}${pad(end.getUTCMinutes())}00Z`;
    const uid = `${String(input.uid || input.day || 'daily')}@english-daily.local`;
    return [
      'BEGIN:VEVENT',
      `UID:${escape(uid)}`,
      `DTSTAMP:${start}`,
      `DTSTART:${start}`,
      `DTEND:${finish}`,
      `SUMMARY:${escape(input.title || 'English Daily practice')}`,
      `DESCRIPTION:${escape(input.description || '')}`,
      'END:VEVENT',
    ].map(fold).join('\r\n');
  }

  function buildCalendar(options) {
    const input = options || {};
    const days = Array.isArray(input.days) ? [...new Set(input.days.map(String).filter(Boolean))].sort() : [];
    const time = input.time || DEFAULT_TIME;
    const brand = input.brand || 'English Daily';
    const goal = Number(input.weeklyGoal) || 5;
    const lines = [
      'BEGIN:VCALENDAR',
      'VERSION:2.0',
      'PRODID:-//English Daily//Study reminders//EN',
      'CALSCALE:GREGORIAN',
      'METHOD:PUBLISH',
      'X-WR-CALNAME:English Daily reminders',
    ];
    for (const day of days) {
      const event = buildEvent({
        day,
        time,
        uid: `${input.lang || 'en'}-${day}`,
        title: `${brand} practice`,
        description: `Read, listen and review ${goal} days this week.`,
      });
      if (event) lines.push(event);
    }
    lines.push('END:VCALENDAR');
    return `${lines.join('\r\n')}\r\n`;
  }

  function download(text, filename, doc) {
    const target = doc || (typeof document !== 'undefined' ? document : null);
    if (!target || !target.createElement) return false;
    const blob = new Blob([text], { type: 'text/calendar;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const link = target.createElement('a');
    link.href = url;
    link.download = filename || 'english-daily-reminders.ics';
    target.body.appendChild(link);
    link.click();
    link.remove();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
    return true;
  }

  return { DEFAULT_TIME, pad, stamp, escape, fold, buildEvent, buildCalendar, download };
})();
