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
      'annotation.hl1': 'Gold highlight',
      'annotation.hl2': 'Blue highlight',
      'annotation.hl3': 'Green highlight',
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
      'tour.home.title': 'Start at home',
      'tour.home.body': 'Today is your home base: choose a level, read, listen and practise.',
      'tour.level.title': 'Choose your level',
      'tour.level.body': 'Start with a CEFR level, then switch any time.',
      'tour.tabs.title': 'Browse the day',
      'tour.tabs.body': 'Read news, culture and history in both text and audio.',
      'tour.phrase.title': 'Learn the phrase',
      'tour.phrase.body': 'Each level has one word, expression and history term.',
      'tour.exercises.title': 'Practise actively',
      'tour.exercises.body': 'Answer three short exercises to review what you learned.',
      'tour.anki.title': 'Export learned items',
      'tour.anki.body': 'Save a phrase, then open the Anki page to send notes or download a tab-separated deck.',
      'tour.glossary.title': 'Build your glossary',
      'tour.glossary.body': 'Star items, export them to Anki, and keep your progress.',
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
      'annotation.hl1': 'Resaltado dorado',
      'annotation.hl2': 'Resaltado azul',
      'annotation.hl3': 'Resaltado verde',
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
      'tour.home.title': 'Empieza desde casa',
      'tour.home.body': 'Hoy es tu punto de partida: elige un nivel, lee, escucha y practica.',
      'tour.level.title': 'Elige tu nivel',
      'tour.level.body': 'Empieza con un nivel CEFR y cámbialo cuando quieras.',
      'tour.tabs.title': 'Explora el día',
      'tour.tabs.body': 'Lee noticias, cultura e historia en texto y audio.',
      'tour.phrase.title': 'Aprende la frase',
      'tour.phrase.body': 'Cada nivel tiene una palabra, una expresión y un término histórico.',
      'tour.exercises.title': 'Practica activamente',
      'tour.exercises.body': 'Responde tres ejercicios breves para repasar lo aprendido.',
      'tour.anki.title': 'Exporta lo aprendido',
      'tour.anki.body': 'Guarda una frase y abre la página Anki para enviar notas o descargar una baraja TSV.',
      'tour.glossary.title': 'Crea tu glosario',
      'tour.glossary.body': 'Marca elementos, expórtalos a Anki y conserva tu progreso.',
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
