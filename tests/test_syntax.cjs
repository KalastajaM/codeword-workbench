'use strict';
const assert = require('node:assert/strict');
const test = require('node:test');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

// Most tests load extracted snippets, so a syntax error elsewhere in a
// browser script would pass them while the page fails to load.
test('Every browser script compiles', () => {
  const dir = path.join(__dirname, '..', 'static');
  const scripts = fs.readdirSync(dir).filter(name => name.endsWith('.js'));
  assert.ok(scripts.includes('app.js'));
  for (const name of scripts) {
    assert.doesNotThrow(() => new vm.Script(fs.readFileSync(path.join(dir, name), 'utf8'), {filename: name}), name);
  }
});
