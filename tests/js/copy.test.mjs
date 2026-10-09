import { test } from 'node:test';
import assert from 'node:assert/strict';
import { heroRegions, rulesFromProfile } from '../../app/static/js/copy.js';

const registry = {
  aa: { label: 'Alpha', color: '#111111', default_on: true },
  bb: { label: 'Beta', color: '#222222', default_on: false },
  cc: { label: 'Gamma', color: '#333333', default_on: true },
};

test('heroRegions keeps default_on regions in the given order', () => {
  assert.deepEqual(heroRegions(registry, ['cc', 'bb', 'aa']), [
    { label: 'Gamma', color: '#333333' },
    { label: 'Alpha', color: '#111111' },
  ]);
});

test('heroRegions skips unknown keys and tolerates empty input', () => {
  assert.deepEqual(heroRegions(registry, ['zz', 'aa']), [{ label: 'Alpha', color: '#111111' }]);
  assert.deepEqual(heroRegions(undefined, undefined), []);
});

const goldilocks = {
  temp_min_c: 7, temp_max_c: 30, temp_min_f: 45, temp_max_f: 86,
  uv_max: 6, rain_max_mm_h: 1, cloud_max_pct: 85, humidity_max_pct: 80, aqi_max: 100,
};

test('rulesFromProfile returns 7 entries for a goldilocks-like rule', () => {
  const rules = rulesFromProfile(goldilocks);
  assert.equal(rules.length, 7);
  for (const r of rules) {
    assert.ok(r.name && r.value && r.sub, JSON.stringify(r));
  }
  const temp = rules.find(r => r.name === 'Comfortable temp');
  assert.match(temp.value, /45/);
  assert.match(temp.value, /86/);
  assert.match(temp.sub, /7/);
  assert.match(temp.sub, /30/);
  assert.match(rules.at(-1).value, /100/);
});

test('rulesFromProfile returns 4 entries when cloud/humidity/aqi are null', () => {
  const rules = rulesFromProfile({
    ...goldilocks, cloud_max_pct: null, humidity_max_pct: null, aqi_max: null,
  });
  assert.equal(rules.length, 4);
});

test('rulesFromProfile with no rule still yields the daytime rule only', () => {
  assert.equal(rulesFromProfile(null).length, 1);
});
