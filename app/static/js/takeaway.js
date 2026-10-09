// Takeaway cards: a pure model (buildTakeaway) and thin DOM renderers.
// Only the render* functions touch the DOM; everything else is node-testable.

import { escapeHtml, fmtValue, prettyBucket } from './format.js';

// Rough number of comfortable hours in a good outdoor day; converts an hours
// gap into "extra outdoor-friendly days". Only meaningful for stay_outside_hours.
export const TYPICAL_GOOD_HOURS_PER_DAY = 8;

export function regionSummary(ys, kind) {
  const vals = ys.filter(v => v != null && Number.isFinite(v));
  if (!vals.length) return { value: null, kind };
  if (kind === 'sum') return { value: vals.reduce((a, b) => a + b, 0), kind };
  if (kind === 'max') return { value: Math.max(...vals), kind };
  // mean / pct / fallback
  return { value: vals.reduce((a, b) => a + b, 0) / vals.length, kind };
}

export function findExtremes(xs, ys) {
  let hiI = -1, loI = -1, hi = -Infinity, lo = Infinity;
  for (let i = 0; i < ys.length; i++) {
    const v = ys[i];
    if (v == null || !Number.isFinite(v)) continue;
    if (v > hi) { hi = v; hiI = i; }
    if (v < lo) { lo = v; loI = i; }
  }
  return {
    hi: hiI >= 0 ? { x: xs[hiI], y: hi } : null,
    lo: loI >= 0 ? { x: xs[loI], y: lo } : null,
  };
}

/**
 * Pure model for the takeaway cards.
 * @param series    {region: {x, y}} as served by /api/series
 * @param visible   region keys currently toggled on
 * @param metricMeta /api/metrics entry ({key, label, unit, kind, better})
 * @param registry  {region: {label, short, color, ink}}
 */
export function buildTakeaway({ series, visible, metricMeta, registry, grain }) {
  const meta = metricMeta || {};
  const kind = meta.kind || 'sum';
  const direction = meta.better === 'higher' || meta.better === 'lower' ? meta.better : null;

  const board = visible
    .filter(r => series[r])
    .map(r => {
      const s = series[r];
      const reg = registry[r] || {};
      return {
        region: r,
        label: reg.label || r,
        short: reg.short || r.slice(0, 3).toUpperCase(),
        color: reg.color || '#888',
        ink: reg.ink || '#555',
        value: regionSummary(s.y, kind).value,
        peak: findExtremes(s.x, s.y).hi,
      };
    })
    .filter(r => r.value != null && Number.isFinite(r.value));

  const ranked = board.sort((a, b) => direction === 'lower' ? a.value - b.value : b.value - a.value);

  let leader = null, trailer = null, gapPct = null, extraDays = null;
  if (ranked.length >= 2) {
    leader = ranked[0];
    trailer = ranked[ranked.length - 1];
    const spread = Math.abs(leader.value - trailer.value);
    const denom = Math.max(Math.abs(leader.value), Math.abs(trailer.value));
    gapPct = denom ? spread / denom * 100 : 0;
    if (meta.key === 'stay_outside_hours' && direction === 'higher') {
      const days = spread / TYPICAL_GOOD_HOURS_PER_DAY;
      if (days >= 1) extraDays = days;
    }
  }

  return {
    metric: meta.key, metricLabel: meta.label || meta.key || '', unit: meta.unit || '',
    grain, ranked, leader, trailer, gapPct, direction, extraDays,
  };
}

const shortName = label => label.replace(/,.*$/, '');

/** els: {text, aux, host} — host is used to create aux when missing. */
export function renderTakeaway(model, els) {
  const { text, host } = els;
  let aux = els.aux;
  if (!aux && host) {
    aux = document.createElement('div');
    aux.id = 'takeaway-aux';
    aux.className = 'takeaway-aux';
    host.appendChild(aux);
  }
  const { ranked, unit, direction } = model;

  if (ranked.length < 2) {
    if (text) text.innerHTML = `<em>${escapeHtml(model.metricLabel)}</em> shown for ${ranked.length ? escapeHtml(ranked[0].label) : 'no counties'}. Toggle another county above to compare.`;
    if (aux) aux.innerHTML = '';
    return;
  }

  const { leader, trailer } = model;
  let headline;
  if (direction) {
    const verb = direction === 'lower' ? 'the least' : 'the most';
    headline = `<span style="color:${escapeHtml(leader.ink)}"><strong>${escapeHtml(shortName(leader.label))}</strong></span> has ${verb} <em>${escapeHtml(model.metricLabel.toLowerCase())}</em> &mdash; <span class="num">${escapeHtml(fmtValue(leader.value, unit))}</span>`;
    if (ranked.length > 2) headline += ` (best of ${ranked.length} counties)`;
    headline += `. <span style="color:${escapeHtml(trailer.ink)}"><strong>${escapeHtml(shortName(trailer.label))}</strong></span> comes last at <span class="num">${escapeHtml(fmtValue(trailer.value, unit))}</span> &mdash; a <span class="num">${escapeHtml(model.gapPct.toFixed(0))}%</span> gap.`;
  } else {
    headline = `<em>${escapeHtml(model.metricLabel)}</em> across ${ranked.length} counties: `;
    headline += ranked.map(r => `<span style="color:${escapeHtml(r.ink)}"><strong>${escapeHtml(r.short)}</strong> <span class="num">${escapeHtml(fmtValue(r.value, unit))}</span></span>`).join(', ') + '.';
  }
  if (text) text.innerHTML = headline;

  const auxBits = [];
  if (ranked.every(r => r.peak)) {
    auxBits.push('Peaks: ' + ranked.slice(0, Math.min(4, ranked.length)).map(r =>
      `<span style="color:${escapeHtml(r.ink)}">${escapeHtml(r.short)} hit <span class="num">${escapeHtml(fmtValue(r.peak.y, unit))}</span> in ${escapeHtml(prettyBucket(r.peak.x, model.grain))}</span>`
    ).join(' · ') + '.');
  }
  if (model.extraDays != null) {
    auxBits.push(`Gap between leader and last: roughly <span class="num">${escapeHtml(model.extraDays.toFixed(0))}</span> extra outdoor-friendly days.`);
  }
  if (aux) aux.innerHTML = auxBits.join(' ');
}

export function renderHeroStats(model, host, rangeLabel) {
  if (!host) return;
  host.innerHTML = '';
  const { ranked, unit, direction } = model;
  ranked.forEach((r, i) => {
    const isLeader = !!direction && i === 0 && ranked.length >= 2;
    const c = document.createElement('div');
    c.className = 'stat';
    c.style.borderTop = `3px solid ${r.color}`;
    if (isLeader) c.classList.add('stat-leader');
    c.innerHTML = `
      <span class="stat-value">${escapeHtml(fmtValue(r.value, unit))}</span>
      <span class="stat-label" style="color:${escapeHtml(r.ink)}">${escapeHtml(r.label.replace(/\s*County/, ''))}${isLeader ? ' ★' : ''}</span>
    `;
    host.appendChild(c);
  });
  const range = document.createElement('div');
  range.className = 'stat stat-range';
  range.innerHTML = `<span class="stat-value">${escapeHtml(rangeLabel)}</span><span class="stat-label">Time range</span>`;
  host.appendChild(range);
}
