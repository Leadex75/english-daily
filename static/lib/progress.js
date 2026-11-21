(function () {
  var KINDS = ['text', 'audio'];

  function contentItems(all, levels, categories) {
    var result = [];
    var levelList = Array.isArray(levels) ? levels : [];
    var categoryList = (Array.isArray(categories) ? categories : []).filter(function (category) {
      return category !== 'phrase';
    });
    levelList.forEach(function (level) {
      var payload = all && all[level];
      var slots = payload && payload.slots;
      if (!slots) return;
      categoryList.forEach(function (category) {
        KINDS.forEach(function (kind) {
          var item = slots[category] && slots[category][kind];
          if (item) result.push(item);
        });
      });
    });
    return result;
  }

  function dailyTotal(all, levels, categories) {
    return contentItems(all, levels, categories).length;
  }

  function dailyDone(all, levels, categories, isDone) {
    return contentItems(all, levels, categories).filter(function (item) {
      return typeof isDone === 'function' && isDone(item);
    }).length;
  }

  function parseDay(value) {
    var match = /^(\d{4})-(\d{2})-(\d{2})/.exec(String(value == null ? '' : value));
    if (!match) return null;
    return new Date(Date.UTC(Number(match[1]), Number(match[2]) - 1, Number(match[3])));
  }

  function practicedDates(entries, reference, days) {
    var end = parseDay(reference);
    if (!end) return [];
    var windowDays = Math.max(1, Number(days) || 7);
    var start = new Date(end.getTime());
    start.setUTCDate(start.getUTCDate() - windowDays + 1);
    var seen = {};
    (Array.isArray(entries) ? entries : []).forEach(function (entry) {
      var value = typeof entry === 'string' ? entry : entry && entry.date;
      var day = parseDay(value);
      if (!day) return;
      if (day < start || day > end) return;
      seen[day.toISOString().slice(0, 10)] = true;
    });
    return Object.keys(seen).sort();
  }

  function weekCount(entries, reference, days) {
    return practicedDates(entries, reference, days).length;
  }

  function percent(count, total) {
    var amount = Number(total) || 0;
    if (amount <= 0) return 0;
    return Math.min(100, Math.round((Number(count) || 0) / amount * 100));
  }

  window.EDProgress = {
    contentItems: contentItems,
    dailyTotal: dailyTotal,
    dailyDone: dailyDone,
    practicedDates: practicedDates,
    weekCount: weekCount,
    percent: percent
  };
}());
