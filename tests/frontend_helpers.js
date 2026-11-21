const assert = require('assert');

global.window = {};
require('../static/lib/links.js');

const EDLinks = global.window.EDLinks;

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

console.log('frontend helper checks passed');
