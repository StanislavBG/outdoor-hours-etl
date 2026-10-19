import { test } from 'node:test';
import assert from 'node:assert/strict';
import { DEFAULT_VIEW, RANGE_ORDER, rangeLabel, rangeLongLabel, readInitialView, viewToParams } from '../src/lib/view.ts';

const fromQuery = (q: string) => {
  const p = new URLSearchParams(q);
  return (k: string) => p.get(k);
};

test('empty URL returns DEFAULT_VIEW', () => {
  const v = readInitialView(fromQuery(''));
  assert.deepEqual(
    { tag: v.tag, grain: v.grain, metric: v.metric, profile: v.profile, yoy: v.yoy },
    DEFAULT_VIEW,
  );
  assert.equal(v.profileFromUrl, false);
  assert.equal(v.regions, null);
});

test('URL values override defaults', () => {
  const v = readInitialView(fromQuery('tag=last5y&grain=monthly&metric=us_aqi_mean&profile=sun_seeker&yoy=1&regions=a,b'));
  assert.equal(v.tag, 'last5y');
  assert.equal(v.grain, 'monthly');
  assert.equal(v.metric, 'us_aqi_mean');
  assert.equal(v.profile, 'sun_seeker');
  assert.equal(v.profileFromUrl, true);
  assert.equal(v.yoy, true);
  assert.deepEqual(v.regions, ['a', 'b']);
});

test('viewToParams omits defaults and keeps non-defaults', () => {
  assert.deepEqual(viewToParams(DEFAULT_VIEW, DEFAULT_VIEW), {});
  assert.deepEqual(
    viewToParams({ tag: 'last1y', grain: 'daily', metric: 'us_aqi_mean', profile: 'goldilocks', yoy: true }, DEFAULT_VIEW),
    { tag: 'last1y', metric: 'us_aqi_mean', yoy: '1' },
  );
  const d = { ...DEFAULT_VIEW, profile: 'sun_seeker' };
  assert.deepEqual(viewToParams({ ...DEFAULT_VIEW, profile: 'sun_seeker' }, d), {});
  assert.deepEqual(viewToParams(DEFAULT_VIEW, d), { profile: 'goldilocks' });
});

test('labels', () => {
  assert.equal(rangeLabel('last1m'), '30 days');
  assert.equal(rangeLongLabel('last1m'), 'Last 30 days');
  assert.equal(rangeLabel('weird'), 'weird');
  assert.equal(rangeLongLabel('weird'), 'weird');
  assert.equal(RANGE_ORDER.length, 6);
});
