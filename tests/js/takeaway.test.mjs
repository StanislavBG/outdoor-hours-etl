import test from 'node:test';
import assert from 'node:assert/strict';
import { buildTakeaway, regionSummary, findExtremes } from '../../app/static/js/takeaway.js';

const registry = {
  a: { label: 'Alpha County, CA', short: 'ALP', color: '#111', ink: '#222' },
  b: { label: 'Beta County, WA', short: 'BET', color: '#333', ink: '#444' },
  c: { label: 'Gamma County, OR', short: 'GAM', color: '#555', ink: '#666' },
};
const series = {
  a: { x: ['2025-01-01', '2025-02-01'], y: [10, 30] },
  b: { x: ['2025-01-01', '2025-02-01'], y: [100, 20] },
  c: { x: ['2025-01-01', '2025-02-01'], y: [null, null] },
};
const meta = (key, better, kind = 'sum') => ({ key, label: key, unit: 'u', kind, better });
const build = (m, visible = ['a', 'b']) =>
  buildTakeaway({ series, visible, metricMeta: m, registry, grain: 'monthly' });

test('higher-better ranks descending', () => {
  const t = build(meta('sunshine_hours', 'higher'));
  assert.equal(t.direction, 'higher');
  assert.deepEqual(t.ranked.map(r => r.region), ['b', 'a']);
  assert.equal(t.leader.region, 'b');
  assert.equal(t.trailer.region, 'a');
  assert.equal(t.gapPct, (120 - 40) / 120 * 100);
  assert.equal(t.ranked[0].short, 'BET');
  assert.deepEqual(t.ranked[0].peak, { x: '2025-01-01', y: 100 });
});

test('lower-better ranks ascending', () => {
  const t = build(meta('precipitation_sum', 'lower'));
  assert.equal(t.direction, 'lower');
  assert.deepEqual(t.ranked.map(r => r.region), ['a', 'b']);
  assert.equal(t.leader.region, 'a');
});

test('neutral metric has null direction', () => {
  const t = build(meta('temperature_2m_mean', null, 'mean'));
  assert.equal(t.direction, null);
  assert.equal(t.ranked.length, 2);
  assert.equal(t.ranked[0].value, 60);
});

test('single visible region has no leader', () => {
  const t = build(meta('sunshine_hours', 'higher'), ['a']);
  assert.equal(t.ranked.length, 1);
  assert.equal(t.leader, null);
  assert.equal(t.trailer, null);
  assert.equal(t.gapPct, null);
  assert.equal(t.extraDays, null);
});

test('all-null regions are excluded', () => {
  const t = build(meta('sunshine_hours', 'higher'), ['a', 'b', 'c']);
  assert.deepEqual(t.ranked.map(r => r.region).sort(), ['a', 'b']);
});

test('extraDays only for stay_outside_hours', () => {
  const s = build(meta('stay_outside_hours', 'higher'));
  assert.equal(s.extraDays, 80 / 8);
  assert.equal(build(meta('sunshine_hours', 'higher')).extraDays, null);
  const small = buildTakeaway({
    series: { a: { x: ['x'], y: [10] }, b: { x: ['x'], y: [12] } },
    visible: ['a', 'b'], metricMeta: meta('stay_outside_hours', 'higher'), registry, grain: 'monthly',
  });
  assert.equal(small.extraDays, null);
});

test('regionSummary and findExtremes helpers', () => {
  assert.equal(regionSummary([1, null, 3], 'sum').value, 4);
  assert.equal(regionSummary([1, null, 3], 'max').value, 3);
  assert.equal(regionSummary([1, null, 3], 'mean').value, 2);
  assert.equal(regionSummary([null], 'sum').value, null);
  assert.deepEqual(findExtremes(['p', 'q'], [5, 9]).hi, { x: 'q', y: 9 });
  assert.equal(findExtremes(['p'], [null]).hi, null);
});
