window.EDQuiz = (() => {
  const PREFIX = 'eds';

  function storageKey(lang, day) {
    return `${PREFIX}.${String(lang || 'en')}.quiz.${String(day || 'today')}`;
  }

  function build(exercises, options) {
    const input = options || {};
    const level = String(input.level || '');
    const limit = Math.max(1, Number(input.limit) || 5);
    const source = Array.isArray(exercises) ? exercises : [];
    return source
      .filter((entry) => entry && (!level || String(entry.level || '') === level))
      .slice(0, limit)
      .map((entry) => ({
        id: String(entry.id || ''),
        kind: String(entry.kind || entry.type || ''),
        level: String(entry.level || ''),
        prompt: String(entry.prompt || ''),
        options: Array.isArray(entry.options) ? entry.options.map(String) : [],
        answer: String(entry.answer || ''),
      }))
      .filter((entry) => entry.id && entry.prompt && entry.answer && entry.options.length);
  }

  function grade(questions, answers) {
    const list = Array.isArray(questions) ? questions : [];
    const given = answers && typeof answers === 'object' ? answers : {};
    const details = list.map((question) => {
      const answer = given[question.id];
      const correct = answer !== undefined && String(answer) === String(question.answer);
      return { id: question.id, answer, expected: question.answer, correct };
    });
    const correct = details.filter((item) => item.correct).length;
    return {
      total: list.length,
      correct,
      wrong: list.length - correct,
      percent: list.length ? Math.round((correct / list.length) * 100) : 0,
      details,
    };
  }

  function saveResult(lang, day, result, store, timestamp) {
    const target = store || window.EDStore;
    const payload = {
      lang: String(lang || 'en'),
      day: String(day || ''),
      total: Number(result && result.total) || 0,
      correct: Number(result && result.correct) || 0,
      percent: Number(result && result.percent) || 0,
      saved_at: String(timestamp || new Date().toISOString()),
    };
    if (target && typeof target.set === 'function') target.set(storageKey(lang, day), payload);
    return payload;
  }

  function loadResult(lang, day, store) {
    const source = store || window.EDStore;
    if (!source || typeof source.get !== 'function') return null;
    return source.get(storageKey(lang, day), null);
  }

  return { PREFIX, storageKey, build, grade, saveResult, loadResult };
})();
