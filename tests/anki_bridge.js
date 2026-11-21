global.window = {};
require('../static/lib/anki.js');

const entry = JSON.parse(process.argv[2] || '{}');
const options = JSON.parse(process.argv[3] || '{}');
process.stdout.write(JSON.stringify(global.window.AnkiExport.buildNote(entry, options)));
