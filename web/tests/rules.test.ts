import { test } from 'node:test';
import assert from 'node:assert/strict';
import { ruleItems, ruleSummary } from '../src/lib/rules.ts';
import type { ProfileRule } from '../src/lib/rules.ts';

const goldilocks: ProfileRule = {
  temp_min_c: 7, temp_max_c: 30, temp_min_f: 45, temp_max_f: 86,
  uv_max: 6, rain_max_mm_h: 1, cloud_max_pct: 85, humidity_max_pct: 80, aqi_max: 100,
};
const open: ProfileRule = { ...goldilocks, cloud_max_pct: null, humidity_max_pct: null, aqi_max: null };

test('Goldilocks rule values', () => {
  const items = ruleItems(goldilocks, { includeUnlimited: true });
  assert.deepEqual(items.map(i => i.key), ['daytime', 'temp', 'uv', 'rain', 'cloud', 'humidity', 'aqi']);
  const v = Object.fromEntries(items.map(i => [i.key, i.value]));
  assert.deepEqual(v, {
    daytime: 'Sun is up', temp: '45°–86°F', uv: 'Index ≤ 6', rain: '≤ 1 mm/hr',
    cloud: 'Cloud ≤ 85%', humidity: 'Humidity ≤ 80%', aqi: 'US AQI ≤ 100',
  });
  assert.match(items[1].sub, /7°–30°C/);
  assert.ok(items.every(i => i.limited));
});

test('null caps give No limit and limited:false', () => {
  const items = ruleItems(open, { includeUnlimited: true });
  for (const k of ['cloud', 'humidity', 'aqi']) {
    const it = items.find(i => i.key === k)!;
    assert.equal(it.value, 'No limit');
    assert.equal(it.limited, false);
  }
});

test('includeUnlimited:false drops null caps', () => {
  assert.deepEqual(ruleItems(open, { includeUnlimited: false }).map(i => i.key), ['daytime', 'temp', 'uv', 'rain']);
});

test('ruleSummary string', () => {
  assert.equal(ruleSummary(goldilocks), 'Temp 45–86°F · UV ≤ 6 · Rain ≤ 1 mm/hr · Cloud ≤ 85% · Humidity ≤ 80% · AQI ≤ 100');
  assert.equal(ruleSummary(open), 'Temp 45–86°F · UV ≤ 6 · Rain ≤ 1 mm/hr');
});
