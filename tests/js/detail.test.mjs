import { test } from 'node:test';
import assert from 'node:assert/strict';
import { renderPairedTable } from '../../app/static/js/detail.js';

const registry = {
  aa: { short: 'AAA', color: '#111111' },
  bb: { short: 'BBB', color: '#222222' },
  cc: { short: 'CCC', color: '#333333' },
};
const order = ['aa', 'bb', 'cc'];
const columns = [
  { key: '_x', label: 'Hour', fmt: 'time', paired: false },
  { key: 'stay', label: 'Stay out', fmt: 'num0', paired: true, leading: true },
  { key: 'pts', label: 'Pts', fmt: 'pts', paired: true },
];
const rows = [{
  _x: '2026-01-01T10:00',
  aa: { stay: 40, pts: 3, n_points: 3 },
  bb: { stay: 90, pts: 1, n_points: 1 },
  cc: { stay: 60, pts: 2, n_points: 3 },
}];

test('renders registry short labels, colours and per-cell n_points', () => {
  const html = renderPairedTable(columns, rows, registry, order);
  for (const s of ['AAA', 'BBB', 'CCC']) assert.ok(html.includes(s));
  assert.ok(html.includes('--region-color:#222222'));
  assert.ok(html.includes('3/3'));
  assert.ok(html.includes('1/1'));
  assert.ok(html.includes('2/3'));
  assert.ok(html.includes('colspan="3"'));
  assert.ok(html.includes('col-region'));
});

test('falls back to 3 when n_points is absent', () => {
  const r = [{ _x: 'x', aa: { pts: 2 }, bb: { pts: 2 }, cc: { pts: 2 } }];
  assert.ok(renderPairedTable(columns, r, registry, order).includes('2/3'));
});

test('escapes HTML in labels', () => {
  const reg = { ...registry, aa: { short: '<b>x</b>', color: '#111' } };
  const cols = [{ key: 'stay', label: '<i>L</i>', fmt: 'num0', paired: true, leading: true }];
  const html = renderPairedTable(cols, rows, reg, order);
  assert.ok(!html.includes('<b>x</b>'));
  assert.ok(!html.includes('<i>L</i>'));
  assert.ok(html.includes('&lt;b&gt;x&lt;/b&gt;'));
});

test('leader class goes to the highest leading value only', () => {
  const html = renderPairedTable(columns, rows, registry, order);
  const leaders = html.match(/<td class="[^"]*\bleader\b[^"]*">[^<]*/g) || [];
  assert.equal(leaders.length, 1);
  assert.ok(leaders[0].includes('>90'));
});

test('drill callback adds data attributes to rows', () => {
  const html = renderPairedTable(columns, rows, registry, order,
    () => ({ grain: 'daily', bucket: '2026-01-01', label: 'Jan 1, 2026' }));
  assert.ok(html.includes('data-grain="daily"'));
  assert.ok(html.includes('data-bucket="2026-01-01"'));
  assert.ok(html.includes('data-label="Jan 1, 2026"'));
  assert.ok(html.includes('drillable'));
});
