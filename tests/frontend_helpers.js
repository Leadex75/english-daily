const assert = require('assert');

global.window = {};
require('../static/lib/branding.js');
require('../static/lib/settings.js');
require('../static/lib/links.js');
require('../static/lib/progress.js');
require('../static/lib/anki.js');

const EDBrand = global.window.EDBrand;
const EDSettings = global.window.EDSettings;
const EDLinks = global.window.EDLinks;
const EDProgress = global.window.EDProgress;
const AnkiExport = global.window.AnkiExport;

assert.strictEqual(EDBrand.brand({ default: 'en' }, 'en'), 'English Daily');
assert.strictEqual(EDBrand.brand({ default: 'en' }, 'es'), 'Spanish Daily');
assert.strictEqual(EDBrand.brand({ brands: { en: 'English Daily' }, default: 'en' }, 'en'), 'English Daily');
assert.strictEqual(EDBrand.route('#archive'), 'archive');
assert.strictEqual(EDBrand.route('settings'), 'settings');
assert.strictEqual(EDBrand.route('#unknown'), 'today');
assert.strictEqual(EDBrand.formatLongDate('2026-11-21'), 'Saturday 21 November 2026');
assert.strictEqual(EDBrand.formatLongDate('bad-date'), '');

assert.strictEqual(EDSettings.KEY, 'english-daily:settings');
assert.strictEqual(EDSettings.normalize({ theme: 'bogus' }).theme, 'system');
assert.strictEqual(EDSettings.normalize({ speed: 1.25 }).speed, 1.25);
assert.strictEqual(EDSettings.normalize({ showFeedback: false }).showFeedback, false);
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
  theme: 'sepia', textSize: 'large', readingFont: 'sans', motion: 'reduce',
});

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

console.log('frontend helper checks passed');
