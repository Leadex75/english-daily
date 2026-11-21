window.EDExercises = (() => {
  function forLevel(payload, level) {
    if (!payload || !Array.isArray(payload.exercises)) return [];
    return payload.exercises.filter((item) => !level || item.level === level);
  }

  function storageKey(exercise) {
    return `${window.EDStore.PREFIX}exercise:${exercise && exercise.id}`;
  }

  function answer(exercise) {
    return exercise ? window.EDStore.get(storageKey(exercise), null) : null;
  }

  function record(exercise, option) {
    if (!exercise) return null;
    const result = {
      id: exercise.id,
      option: String(option),
      correct: String(option) === String(exercise.answer),
      answered_at: new Date().toISOString().slice(0, 10),
    };
    window.EDStore.set(storageKey(exercise), result);
    return result;
  }

  function progress(exercises) {
    const total = (exercises || []).length;
    const done = (exercises || []).filter((item) => answer(item)).length;
    return { done, total, percent: total ? Math.round((done / total) * 100) : 0 };
  }

  return { forLevel, answer, record, progress };
})();
