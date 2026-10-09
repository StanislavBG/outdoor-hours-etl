import test from 'node:test';
import assert from 'node:assert/strict';
import {
  escapeHtml, fmtValue, prettyBucket, toBucket, fmtCell, cellClass,
} from '../../app/static/js/format.js';

test('escapeHtml escapes & < > " and \'', () => {
  assert.equal(escapeHtml(`<a href="x" onclick='y'>&</a>`),
    '&lt;a href=&quot;x&quot; onclick=&#39;y&#39;&gt;&amp;&lt;/a&gt;');
  assert.equal(escapeHtml('plain'), 'plain');
  assert.equal(escapeHtml(null), '');
  assert.equal(escapeHtml(undefined), '');
  assert.equal(escapeHtml(42), '42');
});

test('fmtValue', () => {
  assert.equal(fmtValue(null, 'h'), '—');
  assert.equal(fmtValue(0.5, 'h'), '0.50 h');
  assert.equal(fmtValue(12.34, 'mm'), '12.3 mm');
  assert.match(fmtValue(1234, 'h'), /^1\D?234 h$/);
  assert.equal(fmtValue(0.5), '0.50');
});

test('prettyBucket', () => {
  assert.equal(prettyBucket(2025, 'yearly'), '2025');
  assert.equal(prettyBucket('2025-03-29', 'daily'), 'Mar 29, 2025');
  assert.equal(prettyBucket('2025-03', 'monthly'), 'Mar 2025');
  assert.equal(prettyBucket('2025-03-01', 'monthly'), 'Mar 1, 2025');
  assert.equal(prettyBucket('garbage', 'daily'), 'garbage');
});

test('toBucket', () => {
  assert.equal(toBucket('2025', 'yearly'), '2025');
  assert.equal(toBucket(2025.0, 'yearly'), '2025');
  assert.equal(toBucket('2026-03-29T10:00:00', 'daily'), '2026-03-29');
  assert.equal(toBucket('2026-03-01', 'monthly'), '2026-03-01');
});

test('fmtCell for each fmt', () => {
  assert.equal(fmtCell(3.6, 'num0'), '4');
  assert.equal(fmtCell(3.64, 'num1'), '3.6');
  assert.equal(fmtCell(3.646, 'num2'), '3.65');
  assert.equal(fmtCell(null, 'num1'), '');
  assert.equal(fmtCell('2025-03-29T14:00', 'time'), '14:00');
  assert.equal(fmtCell('n/a', 'time'), 'n/a');
  assert.equal(fmtCell(1, 'bool'), '<span class="yes">✓</span>');
  assert.equal(fmtCell(0, 'bool'), '<span class="no">✗</span>');
  assert.equal(fmtCell(null, 'bool'), '');
  assert.equal(fmtCell(0, 'pts'), '<span class="no">0/3</span>');
  assert.equal(fmtCell(2, 'pts'), '<span class="partial">2/3</span>');
  assert.equal(fmtCell(3, 'pts'), '<span class="yes">3/3</span>');
  assert.equal(fmtCell(null, 'pts'), '');
  assert.equal(fmtCell(7, undefined), '7');
  assert.equal(fmtCell(null, 'unknown'), '');
});

test('cellClass', () => {
  assert.equal(cellClass('bool'), 'bool');
  assert.equal(cellClass('pts'), 'bool');
  assert.equal(cellClass('num1'), 'num');
  assert.equal(cellClass('time'), '');
  assert.equal(cellClass(undefined), '');
});
