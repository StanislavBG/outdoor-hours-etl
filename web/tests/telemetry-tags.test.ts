import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';

const src = readFileSync(new URL('../src/OutdoorHoursPage.tsx', import.meta.url), 'utf8');

test('data-track names are present', () => {
  for (const name of [
    'data-track={`profile-${', 'data-track="profile-custom"', 'data-track="profile-customize"',
    'data-track={`range-${', 'data-track="view-grain"', 'data-track="view-metric"', 'data-track="view-yoy"',
    'data-track={`region-${', 'data-track="tour-open"', 'data-track="detail-fullscreen"', 'data-track="detail-close"',
  ]) assert.ok(src.includes(name), `missing ${name}`);
});

test('trackFlow is created once from host-kit track', () => {
  assert.ok(src.includes("import { track, logError } from 'host-kit'"));
  assert.ok(src.includes("import { makeTrackFlow } from './lib/flow.js'"));
  assert.equal(src.split('makeTrackFlow(track)').length - 1, 1);
});

test('flow steps are emitted', () => {
  for (const [flow, step] of [
    ['profile', 'select'], ['profile', 'rules-shown'], ['custom', 'open'], ['custom', 'recompute-done'],
    ['drill', 'click-point'], ['drill', 'detail-shown'], ['tour', 'open'], ['tour', 'finish'],
  ]) assert.ok(src.includes(`trackFlow('${flow}', '${step}'`), `missing ${flow}.${step}`);
});

test('errors are reported with logError', () => {
  for (const where of ['payload-fetch', 'custom-recompute', 'hourly-day-fetch'])
    assert.ok(src.includes(`where: '${where}'`) || src.includes(`'${where}'`), `missing ${where}`);
});
