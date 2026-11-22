window.EDExercises = (() => {
  function forLevel(payload, level) {
    if (!payload || !Array.isArray(payload.exercises)) return [];
    return payload.exercises.filter((item) => !level || item.level === level);
  }

  function storageKey(exercise, lang) {
    const language = String(lang || 'en');
    const id = exercise && exercise.id;
    if (language === 'en') return `${window.EDStore.PREFIX}exercise:${id}`;
    return `${window.EDStore.PREFIX}exercise:${language}:${id}`;
  }

  function answer(exercise, lang) {
    return exercise ? window.EDStore.get(storageKey(exercise, lang), null) : null;
  }

  function record(exercise, option, lang) {
    if (!exercise) return null;
    const result = {
      id: exercise.id,
      option: String(option),
      correct: String(option) === String(exercise.answer),
      answered_at: new Date().toISOString().slice(0, 10),
    };
    window.EDStore.set(storageKey(exercise, lang), result);
    return result;
  }

  function progress(exercises, lang) {
    const total = (exercises || []).length;
    const done = (exercises || []).filter((item) => answer(item, lang)).length;
    return { done, total, percent: total ? Math.round((done / total) * 100) : 0 };
  }

  return { forLevel, answer, record, progress, storageKey };
})();
