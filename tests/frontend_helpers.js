const assert = require('assert');

global.window = {};
require('../static/lib/links.js');
require('../static/lib/progress.js');

const EDLinks = global.window.EDLinks;
const EDProgress = global.window.EDProgress;

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
