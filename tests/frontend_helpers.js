const assert = require('assert');

global.window = {};
require('../static/lib/store.js');
require('../static/lib/branding.js');
require('../static/lib/settings.js');
require('../static/lib/i18n.js');
require('../static/lib/ics.js');
require('../static/lib/quiz.js');
require('../static/lib/annotations.js');
require('../static/lib/reading.js');
require('../static/lib/shortcuts.js');
require('../static/lib/semester.js');
require('../static/lib/links.js');
require('../static/lib/search.js');
require('../static/lib/archive.js');
require('../static/lib/progress.js');
require('../static/lib/anki.js');
require('../static/js/ankiconnect.js');
require('../static/lib/exercises.js');
require('../static/lib/tour.js');

const EDStore = global.window.EDStore;
const EDBrand = global.window.EDBrand;
const EDSettings = global.window.EDSettings;
const EDi18n = global.window.EDi18n;
const EDICS = global.window.EDICS;
const EDQuiz = global.window.EDQuiz;
const EDAnnotations = global.window.EDAnnotations;
const EDReading = global.window.EDReading;
const EDShortcuts = global.window.EDShortcuts;
const EDSemester = global.window.EDSemester;
const EDLinks = global.window.EDLinks;
const EDSearch = global.window.EDSearch;
const EDArchive = global.window.EDArchive;
const EDProgress = global.window.EDProgress;
const AnkiExport = global.window.AnkiExport;
const AnkiConnect = global.window.AnkiConnect;
const EDAnkiConnect = global.window.EDAnkiConnect;
const EDExercises = global.window.EDExercises;
const EDTour = global.window.EDTour;

const payload = {
  default: 'en',
  languages: ['en', 'es'],
  labels: { en: 'English', es: 'Español' },
  metadata: {
    en: { brand: 'English Daily', tagline: 'A little English, every day.' },
    es: { brand: 'Spanish Daily', tagline: 'Un poco de español, cada día.' },
  },
};

assert.deepStrictEqual(EDBrand.languageCodes(payload), ['en', 'es']);
assert.deepStrictEqual(EDBrand.languageCodes({}), ['en']);
assert.strictEqual(EDBrand.defaultLanguage(payload), 'en');
assert.strictEqual(EDBrand.defaultLanguage({ default: 'es', languages: ['es', 'en'] }), 'es');
assert.strictEqual(EDBrand.normalizeLanguage('es', payload), 'es');
assert.strictEqual(EDBrand.normalizeLanguage('fr', payload), 'en');
assert.strictEqual(EDBrand.normalizeLanguage('fr', { default: 'es', languages: ['es'] }), 'es');
assert.strictEqual(EDBrand.languageLabel(payload, 'es'), 'Español');
assert.strictEqual(EDBrand.languageLabel({}, 'es'), 'Español');
assert.deepStrictEqual(EDBrand.languageOptions(payload), [
  { code: 'en', label: 'English' },
  { code: 'es', label: 'Español' },
]);
assert.strictEqual(EDBrand.brand({ default: 'en' }, 'en'), 'English Daily');
assert.strictEqual(EDBrand.brand({ default: 'en' }, 'es'), 'Spanish Daily');
assert.strictEqual(EDBrand.brand({ brands: { en: 'English Daily' }, default: 'en' }, 'en'), 'English Daily');
assert.strictEqual(EDBrand.tagline({ default: 'en' }, 'en'), 'A little English, every day.');
assert.strictEqual(EDBrand.tagline({ default: 'en' }, 'es'), 'Un poco de español, cada día.');
assert.strictEqual(EDBrand.tagline(payload, 'es'), 'Un poco de español, cada día.');
assert.strictEqual(EDBrand.route('#archive'), 'archive');
assert.strictEqual(EDBrand.route('#semester'), 'semester');
assert.strictEqual(EDBrand.route('settings'), 'settings');
assert.strictEqual(EDBrand.route('#unknown'), 'today');
assert.strictEqual(EDBrand.formatLongDate('2026-11-21'), 'Saturday 21 November 2026');
assert.strictEqual(EDBrand.formatLongDate('bad-date'), '');

assert.strictEqual(EDSettings.KEY, 'english-daily:settings');
assert.strictEqual(EDSettings.normalize({ theme: 'bogus' }).theme, 'system');
assert.strictEqual(EDSettings.normalize({ speed: 1.25 }).speed, 1.25);
assert.strictEqual(EDSettings.normalize({ showFeedback: false }).showFeedback, false);
assert.strictEqual(EDSettings.normalize({ readingMode: true }).readingMode, true);
assert.strictEqual(EDSettings.normalize({ reminderTime: 'bad' }).reminderTime, '07:00');
assert.strictEqual(EDSettings.normalize({ ankiConnectUrl: 'ftp://bad' }).ankiConnectUrl, 'http://127.0.0.1:8765');
const settingsStore = new Map();
const fakeSettingsStore = {
  get: (key, fallback) => settingsStore.has(key) ? settingsStore.get(key) : fallback,
  set: (key, value) => settingsStore.set(key, value),
};
const savedSettings = EDSettings.save({
  theme: 'sepia', textSize: 'large', readingFont: 'sans', speed: 0.8, reduceMotion: true,
}, fakeSettingsStore);
assert.deepStrictEqual(EDSettings.load(fakeSettingsStore), savedSettings);
const settingsRoot = { dataset: {} };
EDSettings.apply(savedSettings, settingsRoot);
assert.deepStrictEqual(settingsRoot.dataset, {
  theme: 'sepia', textSize: 'large', readingFont: 'sans', motion: 'reduce', reading: 'off',
});

assert.strictEqual(EDArchive.monthKey('2026-11-21'), '2026-11');
assert.strictEqual(EDArchive.shiftMonth('2026-01', -1), '2025-12');
assert.deepStrictEqual(EDArchive.months(['2026-11-21', '2026-10-05', '2026-11-20']), ['2026-10', '2026-11']);
const archiveDays = ['2026-11-21', '2026-11-20', '2026-10-05'];
const november = EDArchive.buildMonth('2026-11', archiveDays, '2026-11-21', '2026-11-21');
assert.strictEqual(november.label, 'November 2026');
assert.strictEqual(november.availableCount, 2);
assert.strictEqual(november.cells.length % 7, 0);
assert.deepStrictEqual(november.cells.filter((cell) => cell.available).map((cell) => cell.date), ['2026-11-20', '2026-11-21']);
assert.strictEqual(november.cells.filter((cell) => cell.selected).length, 1);
assert.strictEqual(november.cells.filter((cell) => cell.today).length, 1);
assert.deepStrictEqual(EDArchive.recentDates(archiveDays, 2), ['2026-11-21', '2026-11-20']);

const mergedSearch = EDSearch.merge([
  { items: [{ date: '2026-11-20', guid_hash: 'a', title: 'Earlier', body: 'alpha' }] },
  { items: [
    { date: '2026-11-21', guid_hash: 'b', title: 'Later', body: 'alpha' },
    { date: '2026-11-20', guid_hash: 'a', title: 'Earlier', body: 'alpha' },
  ] },
]);
assert.strictEqual(mergedSearch.items.length, 2);
assert.strictEqual(mergedSearch.items[0].date, '2026-11-21');
assert.strictEqual(EDSearch.query(mergedSearch, 'alpha', null, 10).length, 2);

assert.strictEqual(EDLinks.label('text'), 'Read the full text');
assert.strictEqual(EDLinks.label('audio'), 'Listen to the original audio');
assert.strictEqual(EDLinks.label('other'), 'Read the full text');
assert.strictEqual(EDLinks.source({ source: 'BBC News' }), 'BBC News');
assert.strictEqual(EDLinks.source({}), 'the publisher');
assert.strictEqual(EDLinks.hasUrl({ url: 'https://example.org/story' }), true);
assert.strictEqual(EDLinks.hasUrl({}), false);
assert.deepStrictEqual(
  EDLinks.describe({ source: 'The Guardian', url: 'https://example.org/audio' }, 'audio'),
  { label: 'Listen to the original audio', source: 'The Guardian', url: 'https://example.org/audio' }
);

assert.strictEqual(AnkiExport.available(), true);
assert.strictEqual(AnkiExport.status({ learned: true }, (item) => item.learned, true), 'Ready for Anki');
assert.strictEqual(
  AnkiExport.status({ learned: false }, (item) => item.learned, true),
  'Mark learned before exporting to Anki'
);
assert.strictEqual(AnkiExport.status({}, () => true, false), 'Anki export unavailable offline');
assert.deepStrictEqual(
  AnkiExport.select(
    [{ text: 'learned', learned: true }, { text: 'new', learned: false }],
    (item) => item.learned,
    (item) => item.text
  ),
  ['learned']
);
assert.strictEqual(AnkiExport.toTsv([{ front: 'word', back: 'mot' }]), 'word\tmot');

const ankiEntry = {
  key: 'en-word-bridge',
  text: 'bridge <a>',
  meaning_fr: 'pont',
  example: 'We crossed the bridge.',
  level: 'B1',
  learned_at: '2026-11-21',
};
const ankiOptions = { lang: 'en', day: '2026-11-21' };
const ankiNote = AnkiExport.buildNote(ankiEntry, ankiOptions);
assert.strictEqual(ankiNote.guid.length, 32);
assert.deepStrictEqual(ankiNote.fields.Front, 'bridge &lt;a&gt;');
assert.strictEqual(ankiNote.fields.Back, 'pont');
assert.deepStrictEqual(AnkiExport.buildNote(ankiEntry, ankiOptions), ankiNote);
assert.strictEqual(AnkiExport.buildNotes([ankiEntry, ankiEntry], ankiOptions).length, 1);
assert.strictEqual(AnkiExport.ankiConnectNote(ankiNote).options.duplicateScope, 'deck');
const ankiStore = new Map();
const fakeAnkiStore = {
  get: (key, fallback) => ankiStore.has(key) ? ankiStore.get(key) : fallback,
  set: (key, value) => ankiStore.set(key, value),
};
AnkiExport.recordExport([ankiNote], fakeAnkiStore, [true]);
assert.strictEqual(AnkiExport.exportStatus(ankiNote, fakeAnkiStore).added, 1);

async function testAnkiConnect() {
  const calls = [];
  const client = AnkiConnect('http://127.0.0.1:8765/', function (url, init) {
    const payload = JSON.parse(init.body);
    calls.push({ url, action: payload.action, version: payload.version, notes: payload.params.notes });
    return Promise.resolve({
      ok: true,
      status: 200,
      json: () => Promise.resolve({ result: payload.action === 'version' ? 6 : [true, false] }),
    });
  });
  assert.strictEqual(await client.check(), 6);
  assert.deepStrictEqual(await client.addNotes([ankiNote]), [true, false]);
  assert.deepStrictEqual(calls.map((call) => call.action), ['version', 'addNotes']);
  assert.strictEqual(calls[1].url, 'http://127.0.0.1:8765');
  assert.strictEqual(calls[1].notes[0].fields.Front, 'bridge &lt;a&gt;');
}

async function testAddendumAnkiConnect() {
  const calls = [];
  const directClient = EDAnkiConnect.createClient({
    url: 'http://127.0.0.1:8765/',
    proxyUrl: null,
    fetchImpl: function (url, init) {
      const payload = JSON.parse(init.body);
      calls.push({ url, action: payload.action, headers: init.headers, params: payload.params });
      const results = {
        version: 6,
        requestPermission: null,
        modelFieldNames: ['Front', 'Back', 'Example', 'Source', 'Level', 'Language', 'Date', 'Guid'],
        createModel: null,
        addNotes: [11, null, false],
      };
      return Promise.resolve({
        ok: true,
        status: 200,
        json: () => Promise.resolve({ result: results[payload.action], error: null }),
      });
    },
  });
  const details = await directClient.check();
  assert.strictEqual(details.version, 6);
  assert.strictEqual(details.mode, 'direct');
  await directClient.requestPermission();
  const models = await directClient.verifyModels([{ modelName: 'English Daily Phrase' }]);
  assert.deepStrictEqual(models[0].missing, []);
  const summary = await directClient.addNotes([{}, {}, {}]);
  assert.deepStrictEqual(summary, { total: 3, added: 1, duplicates: 2, failed: 0, results: [11, null, false] });
  assert.strictEqual(calls[0].headers['Content-Type'], 'text/plain');
  assert.deepStrictEqual(calls.map((call) => call.action), [
    'version', 'requestPermission', 'modelFieldNames', 'addNotes',
  ]);

  const proxyCalls = [];
  let modelsFetched = false;
  const proxyClient = EDAnkiConnect.createClient({
    fetchImpl: function (url, init) {
      if (init.method === 'GET') {
        modelsFetched = true;
        return Promise.resolve({
          ok: true,
          status: 200,
          json: () => Promise.resolve({ models: [{ modelName: 'English Daily Phrase', inOrderFields: ['Front', 'Back'] }] }),
        });
      }
      const payload = JSON.parse(init.body);
      proxyCalls.push({ url, action: payload.action, contentType: init.headers['Content-Type'] });
      return Promise.resolve({
        ok: true,
        status: 200,
        json: () => Promise.resolve({
          result: payload.action === 'version' ? 6 : payload.action === 'modelFieldNames' ? ['Front'] : null,
          error: null,
        }),
      });
    },
  });
  const proxyDetails = await proxyClient.check();
  assert.strictEqual(proxyDetails.mode, 'proxy');
  assert.strictEqual(proxyCalls[0].url, './api/ankiconnect');
  assert.strictEqual(proxyCalls[0].contentType, 'application/json');
  await proxyClient.verifyModels([{ modelName: 'English Daily Phrase' }]);
  assert.strictEqual(modelsFetched, true);
  assert.strictEqual(proxyCalls.some((call) => call.action === 'createModel'), true);
  assert.ok(EDAnkiConnect.diagnostic({ status: 403 }).includes('webCorsOriginList'));
  assert.ok(EDAnkiConnect.diagnostic(new Error('AnkiConnect permission not granted')).includes('AnkiConnect'));
}

const levels = ['A1', 'A2', 'B1', 'B2', 'C1', 'C2'];
const categories = ['news', 'culture', 'history', 'phrase'];
const slotOrder = [];
for (const category of categories.filter((item) => item !== 'phrase')) {
  slotOrder.push([category, 'text'], [category, 'audio']);
}
const all = {};
const counts = [4, 2, 2, 2, 2, 2];
let nextId = 1;
levels.forEach((level, index) => {
  const slots = {};
  for (const category of categories.filter((item) => item !== 'phrase')) {
    slots[category] = { text: null, audio: null };
  }
  for (let i = 0; i < counts[index]; i += 1) {
    const [category, kind] = slotOrder[i];
    slots[category][kind] = { id: `${level}-${nextId}` };
    nextId += 1;
  }
  all[level] = {
    slots,
    phrase: { word: { key: 'word' }, expression: { key: 'expression' }, history: { key: 'history' } }
  };
});
const contentItems = EDProgress.contentItems(all, levels, categories);
assert.strictEqual(contentItems.length, 14);
assert.strictEqual(EDProgress.dailyTotal(all, levels, categories), 14);
contentItems.slice(0, 5).forEach((item) => { item.done = true; });
assert.strictEqual(EDProgress.dailyDone(all, levels, categories, (item) => item.done), 5);
assert.strictEqual(EDProgress.percent(7, 14), 50);
assert.strictEqual(EDProgress.percent(0, 0), 0);

const exerciseStore = new Map();
const fakeLocalStorage = {
  getItem(key) { return exerciseStore.has(key) ? exerciseStore.get(key) : null; },
  setItem(key, value) { exerciseStore.set(key, String(value)); },
  removeItem(key) { exerciseStore.delete(key); },
  key(index) { return Array.from(exerciseStore.keys())[index] || null; },
  get length() { return exerciseStore.size; },
};
global.window.localStorage = fakeLocalStorage;
global.localStorage = fakeLocalStorage;
EDStore.keys(EDStore.PREFIX).forEach((key) => EDStore.remove(key));

const tourSteps = [{ id: 'home', target: '[data-eds-today]' }, { id: 'level', target: '[data-eds-level]' }];
assert.deepStrictEqual(EDTour.steps({ tour: tourSteps }), tourSteps);
assert.deepStrictEqual(EDTour.state(), { index: 0, open: false });
assert.deepStrictEqual(EDTour.start(1), { index: 1, open: true });
assert.deepStrictEqual(EDTour.advance(2), { index: 2, open: false });
assert.deepStrictEqual(EDTour.go(0), { index: 0, open: true });
assert.deepStrictEqual(EDTour.end(), { index: 0, open: false });
assert.strictEqual(EDTour.seen(), false);
assert.strictEqual(EDTour.markSeen(), true);
assert.strictEqual(EDTour.seen(), true);
assert.strictEqual(EDStore.get('english-daily:tour:seen'), true);
EDStore.keys(EDStore.PREFIX).forEach((key) => EDStore.remove(key));

const ex = { id: 'ex-1', answer: 'yes' };
EDExercises.record(ex, 'yes', 'en');
assert.strictEqual(EDExercises.storageKey(ex, 'en'), 'english-daily:exercise:ex-1');
assert.strictEqual(EDExercises.answer(ex, 'en').correct, true);
assert.strictEqual(EDExercises.answer(ex, 'es'), null);
EDExercises.record(ex, 'no', 'es');
assert.strictEqual(EDExercises.storageKey(ex, 'es'), 'english-daily:exercise:es:ex-1');
assert.strictEqual(EDExercises.answer(ex, 'es').correct, false);
assert.strictEqual(EDExercises.answer(ex, 'en').correct, true);

const practiced = [
  '2026-11-21',
  '2026-11-21',
  { date: '2026-11-20' },
  { date: '2026-11-19' },
  { date: '2026-11-01' },
  { date: 'not-a-date' }
];
assert.deepStrictEqual(
  EDProgress.practicedDates(practiced, '2026-11-21', 7),
  ['2026-11-19', '2026-11-20', '2026-11-21']
);
assert.strictEqual(EDProgress.weekCount(practiced, '2026-11-21', 7), 3);

function testAddendumPhaseEleven() {
  assert.strictEqual(EDi18n.t('en', 'quiz.result', { correct: 1, total: 2, percent: 50 }), '1 / 2 correct (50%).');
  EDi18n.setOverride('en', 'quiz.check', 'Verify', EDStore);
  assert.strictEqual(EDi18n.t('en', 'quiz.check', {}, EDStore), 'Verify');

  const calendar = EDICS.buildCalendar({
    days: ['2026-11-21'],
    lang: 'en',
    brand: 'English Daily',
    time: '07:00',
  });
  assert.ok(calendar.startsWith('BEGIN:VCALENDAR\r\n'));
  assert.ok(calendar.includes('UID:en-2026-11-21@english-daily.local'));
  assert.ok(calendar.includes('DTSTART:20261121T070000Z'));
  assert.strictEqual(calendar, EDICS.buildCalendar({
    days: ['2026-11-21'],
    lang: 'en',
    brand: 'English Daily',
    time: '07:00',
  }));

  const questions = EDQuiz.build([
    { id: 'q1', level: 'B1', prompt: 'Choose one', options: ['yes', 'no'], answer: 'yes' },
    { id: 'q2', level: 'B1', prompt: 'Choose another', options: ['yes', 'no'], answer: 'no' },
    { id: 'q3', level: 'A2', prompt: 'Skip me', options: ['yes', 'no'], answer: 'yes' },
  ], { level: 'B1', limit: 1 });
  assert.strictEqual(questions.length, 1);
  const graded = EDQuiz.grade(questions, { q1: 'yes' });
  assert.strictEqual(graded.correct, 1);
  const quizResult = EDQuiz.saveResult('en', '2026-11-21', graded, EDStore, '2026-11-21T08:00:00Z');
  assert.strictEqual(quizResult.total, 1);
  assert.deepStrictEqual(EDQuiz.loadResult('en', '2026-11-21', EDStore), quizResult);

  const note = EDAnnotations.save({
    lang: 'en', day: '2026-11-21', item: 'news-1', text: 'Useful phrase', saved_at: '2026-11-21T08:00:00Z',
  }, EDStore);
  assert.ok(note.id);
  assert.strictEqual(EDAnnotations.list(EDStore, 'en', '2026-11-21').length, 1);
  assert.strictEqual(EDAnnotations.summary(EDStore, 'en', '2026-11-21').items, 1);
  assert.strictEqual(EDAnnotations.remove(note.id, EDStore, 'en', '2026-11-21'), 1);
  assert.strictEqual(EDAnnotations.list(EDStore, 'en', '2026-11-21').length, 0);

  const readingRoot = { dataset: {} };
  assert.strictEqual(EDReading.apply(true, readingRoot), 'focus');
  assert.strictEqual(EDReading.isEnabled(readingRoot), true);
  assert.strictEqual(EDReading.toggle(readingRoot), 'off');

  assert.strictEqual(EDShortcuts.parse({ key: 'r', target: { tagName: 'BODY' } }), 'r');
  assert.strictEqual(EDShortcuts.parse({ key: 'r', target: { tagName: 'INPUT' } }), '');
  const shortcutCalls = [];
  EDShortcuts.dispatch({ key: 'r', target: { tagName: 'BODY' } }, {
    readingMode: () => shortcutCalls.push('readingMode'),
  });
  assert.deepStrictEqual(shortcutCalls, ['readingMode']);

  const semester = { start: '2026-11-01', end: '2026-11-14', weeklyGoal: 5 };
  assert.strictEqual(EDSemester.weeks(semester).length, 2);
  const semesterProgress = EDSemester.progress(['2026-11-02', '2026-11-02', '2026-11-03'], semester);
  assert.strictEqual(semesterProgress.completed, 2);
  assert.strictEqual(semesterProgress.goal, 10);
  assert.strictEqual(semesterProgress.percent, 20);
  assert.strictEqual(semesterProgress.weeks[0].count, 2);
  const savedSemester = EDSemester.save('en', semester, EDStore, '2026-11-21T08:00:00Z');
  assert.strictEqual(EDSemester.load('en', EDStore).start, savedSemester.start);
  assert.strictEqual(EDSemester.load('en', EDStore).end, savedSemester.end);
  assert.strictEqual(EDSemester.load('en', EDStore).weeklyGoal, savedSemester.weeklyGoal);

  EDStore.keys('eds.').forEach((key) => EDStore.remove(key));
}

testAnkiConnect().then(testAddendumAnkiConnect).then(testAddendumPhaseEleven).then(function () {
  console.log('frontend helper checks passed');
}).catch(function (err) {
  console.error(err);
  process.exit(1);
});
