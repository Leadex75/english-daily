window.EDi18n = (() => {
  const PREFIX = 'eds';
  const STRINGS = {
    en: {
      'control.reading': 'Reading mode',
      'quiz.title': 'Daily quiz',
      'quiz.check': 'Check answers',
      'quiz.empty': 'Answer a few exercises, then check your score.',
      'quiz.result': '{correct} / {total} correct ({percent}%).',
      'annotation.title': 'My notes',
      'annotation.placeholder': 'Write a note about this text',
      'annotation.save': 'Save note',
      'annotation.empty': 'No notes for this day yet.',
      'annotation.remove': 'Remove note',
      'semester.tab': 'Semester',
      'semester.title': 'Semester planner',
      'semester.intro': 'Choose a date range and a weekly goal. Progress is stored only in this browser.',
      'semester.start': 'Start date',
      'semester.end': 'End date',
      'semester.goal': 'Days per week',
      'semester.save': 'Save plan',
      'semester.progress': '{completed} of {goal} days ({percent}%)',
      'shortcuts.title': 'Keyboard shortcuts',
      'shortcuts.open': 'Show shortcuts',
      'shortcuts.close': 'Close',
      'shortcuts.previousDay': 'Previous day',
      'shortcuts.nextDay': 'Next day',
      'shortcuts.tabNews': 'News tab',
      'shortcuts.tabCulture': 'Culture tab',
      'shortcuts.tabHistory': 'History tab',
      'shortcuts.tabPhrase': 'Phrase tab',
      'shortcuts.tabArchive': 'Archive tab',
      'shortcuts.annotation': 'Focus notes',
      'shortcuts.checkQuiz': 'Check quiz',
      'reminders.time': 'Reminder time',
      'reminders.download': 'Download reminders',
    },
    es: {
      'control.reading': 'Modo lectura',
      'quiz.title': 'Cuestionario diario',
      'quiz.check': 'Comprobar respuestas',
      'quiz.empty': 'Responde algunos ejercicios y comprueba tu resultado.',
      'quiz.result': '{correct} de {total} correctas ({percent}%).',
      'annotation.title': 'Mis notas',
      'annotation.placeholder': 'Escribe una nota sobre este texto',
      'annotation.save': 'Guardar nota',
      'annotation.empty': 'Aún no hay notas para este día.',
      'annotation.remove': 'Eliminar nota',
      'semester.tab': 'Semestre',
      'semester.title': 'Planificador del semestre',
      'semester.intro': 'Elige un rango de fechas y una meta semanal. El progreso se guarda solo en este navegador.',
      'semester.start': 'Fecha de inicio',
      'semester.end': 'Fecha final',
      'semester.goal': 'Días por semana',
      'semester.save': 'Guardar plan',
      'semester.progress': '{completed} de {goal} días ({percent}%)',
      'shortcuts.title': 'Atajos de teclado',
      'shortcuts.open': 'Ver atajos',
      'shortcuts.close': 'Cerrar',
      'shortcuts.previousDay': 'Día anterior',
      'shortcuts.nextDay': 'Día siguiente',
      'shortcuts.tabNews': 'Pestaña Noticias',
      'shortcuts.tabCulture': 'Pestaña Cultura',
      'shortcuts.tabHistory': 'Pestaña Historia',
      'shortcuts.tabPhrase': 'Pestaña Frase',
      'shortcuts.tabArchive': 'Pestaña Archivo',
      'shortcuts.annotation': 'Enfocar notas',
      'shortcuts.checkQuiz': 'Comprobar cuestionario',
      'reminders.time': 'Hora del recordatorio',
      'reminders.download': 'Descargar recordatorios',
    },
  };

  function storageKey(lang) {
    return `${PREFIX}.${String(lang || 'en')}.i18n`;
  }

  function bundle(lang) {
    return STRINGS[String(lang || 'en')] || STRINGS.en;
  }

  function overrides(lang, store) {
    const source = store || window.EDStore;
    const value = source && typeof source.get === 'function' ? source.get(storageKey(lang), {}) : {};
    return value && typeof value === 'object' ? value : {};
  }

  function setOverride(lang, key, value, store) {
    const target = store || window.EDStore;
    const custom = overrides(lang, target);
    custom[String(key)] = String(value);
    if (target && typeof target.set === 'function') target.set(storageKey(lang), custom);
    return custom;
  }

  function t(lang, key, params, store) {
    const custom = overrides(lang, store);
    let value = Object.prototype.hasOwnProperty.call(custom, key) ? String(custom[key]) : bundle(lang)[key];
    if (value === undefined) value = STRINGS.en[key] || String(key);
    const values = params && typeof params === 'object' ? params : {};
    for (const name of Object.keys(values)) {
      value = value.split(`{${name}}`).join(String(values[name]));
    }
    return value;
  }

  return { PREFIX, STRINGS, storageKey, bundle, overrides, setOverride, t };
})();
