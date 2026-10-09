import { test } from 'node:test';
import assert from 'node:assert/strict';
import { buildTraces, layoutFor } from '../../app/static/js/chart.js';

const registry = { aa: { color: '#111111' }, bb: { color: '#222222' }, cc: { color: '#333333' } };
const data = {
  tag: 'last10y', metric: 'stay_outside_hours', metric_label: 'Stay <out>', unit: 'h',
  series: {
    aa: { label: 'AA', x: [2020, 2021], y: [1, 2] },
    bb: { label: 'BB', x: [2020, 2021], y: [3, 4] },
    cc: { label: 'CC', x: [2020, 2021], y: [5, 6] },
  },
};

test('buildTraces emits only visible regions in given order with registry colours', () => {
  const t = buildTraces(data, ['cc', 'aa'], registry, 'daily');
  assert.deepEqual(t.map(x => x.meta), ['cc', 'aa']);
  assert.equal(t[0].line.color, '#333333');
  assert.equal(t[1].marker.color, '#111111');
});

test('buildTraces skips visible regions missing from data', () => {
  const t = buildTraces(data, ['aa', 'zz'], registry, 'daily');
  assert.deepEqual(t.map(x => x.meta), ['aa']);
});

test('yearly markers are larger than daily', () => {
  const y = buildTraces(data, ['aa'], registry, 'yearly')[0].marker.size;
  const d = buildTraces(data, ['aa'], registry, 'daily')[0].marker.size;
  assert.ok(y > d);
});

test('hovertemplate escapes labels', () => {
  const t = buildTraces(data, ['aa'], registry, 'daily')[0];
  assert.ok(t.hovertemplate.includes('Stay &lt;out&gt;'));
});

test('layoutFor sets tozero only for stay_outside_hours', () => {
  assert.equal(layoutFor(data, 'daily').yaxis.rangemode, 'tozero');
  assert.equal(layoutFor({ ...data, metric: 'pm25' }, 'daily').yaxis.rangemode, undefined);
  assert.equal(layoutFor(data, 'yearly').xaxis.type, 'linear');
  assert.ok(layoutFor(data, 'daily').title.text.includes('Stay &lt;out&gt;'));
});
