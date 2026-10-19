import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';

const src = readFileSync(new URL('../src/OutdoorHoursPage.tsx', import.meta.url), 'utf8');

test('controls render under the profile bar, above hero and leaderboard', () => {
  const marks = ['{/* Global profile toggle', '{/* Controls — sticky on scroll', '{/* Hero */}', '<Leaderboard payload'];
  const idx = marks.map(m => src.indexOf(m));
  idx.forEach((i, n) => assert.notEqual(i, -1, `missing marker ${marks[n]}`));
  for (let n = 1; n < idx.length; n++) assert.ok(idx[n - 1] < idx[n], `${marks[n - 1]} must precede ${marks[n]}`);
});

test('controls section stays sticky', () => {
  assert.match(src, /mt-4[^"]*sticky top-0 z-30/);
});
