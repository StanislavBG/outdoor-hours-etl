import { test } from 'node:test';
import assert from 'node:assert/strict';
import { isFlowName, makeTrackFlow } from '../src/lib/flow.ts';

type Call = [string, Record<string, unknown>];

function setup() {
  const calls: Call[] = [];
  const trackFlow = makeTrackFlow((name, props) => {
    calls.push([name, props]);
  });
  return { calls, trackFlow };
}

test('isFlowName accepts kebab-case names up to 40 chars', () => {
  for (const s of ['a', '0', 'view-change', 'a-b-c', 'a'.repeat(40)]) {
    assert.equal(isFlowName(s), true, s);
  }
});

test('isFlowName rejects uppercase, empty, too long, leading dash', () => {
  for (const s of ['Upper', 'aB', '', 'a'.repeat(41), '-lead', 'has space', 'dot.ted', 'under_score']) {
    assert.equal(isFlowName(s), false, s);
  }
});

test('trackFlow emits <flow>.<step> with merged props', () => {
  const { calls, trackFlow } = setup();
  trackFlow('range-select', 'open', { zone: 'mia' });
  assert.deepEqual(calls, [['range-select.open', { zone: 'mia', flow: 'range-select', step: 'open' }]]);
});

test('trackFlow works without props', () => {
  const { calls, trackFlow } = setup();
  trackFlow('boot', 'ready');
  assert.deepEqual(calls, [['boot.ready', { flow: 'boot', step: 'ready' }]]);
});

test('flow and step override colliding props', () => {
  const { calls, trackFlow } = setup();
  trackFlow('a', 'b', { flow: 'x', step: 'y' });
  assert.deepEqual(calls[0][1], { flow: 'a', step: 'b' });
});

test('invalid flow or step is silently dropped', () => {
  const { calls, trackFlow } = setup();
  trackFlow('Upper', 'ok');
  trackFlow('ok', '');
  trackFlow('ok', 'a'.repeat(41));
  trackFlow('-bad', 'ok');
  trackFlow('ok', '-bad');
  assert.equal(calls.length, 0);
});
