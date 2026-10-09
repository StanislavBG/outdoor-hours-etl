import { escapeHtml, fmtValue, toBucket } from './js/format.js';
import { createDetailPanel } from './js/detail.js';
import { buildTraces, layoutFor, renderChart, clearChart } from './js/chart.js';
import { buildTakeaway, renderTakeaway, renderHeroStats } from './js/takeaway.js';

// Friendly ordered list of ranges the UI surfaces. Unknown server tags still
// show up at the end of the picker.
const RANGE_ORDER = [
  { tag: 'last30y',         label: '30 yrs' },
  { tag: 'last10y',         label: '10 yrs' },
  { tag: 'last5y',          label: '5 yrs' },
  { tag: 'last3y',          label: '3 yrs' },
  { tag: 'last1y',          label: '1 yr' },
  { tag: 'sample_last30',   label: '30 days' },
];

const state = {
  tags: [],              // server tags available on disk
  metrics: [],
  regionRegistry: {},    // {region_key: {label, short, color, ink, default_on}}
  regionOrder: [],       // canonical display order
  regionsOn: new Set(),  // currently visible regions
  tag: null,             // currently selected dataset
};

let panel = null; // detail drill-down, created on DOMContentLoaded

function regionColor(key) { return state.regionRegistry[key]?.color || '#888'; }
function regionInk(key)   { return state.regionRegistry[key]?.ink   || '#555'; }
function regionLabel(key) { return state.regionRegistry[key]?.label || key; }
function regionShort(key) { return state.regionRegistry[key]?.short || key.slice(0, 3).toUpperCase(); }

function visibleRegions() {
  return state.regionOrder.filter(r => state.regionsOn.has(r));
}

async function j(url, opts) {
  const r = await fetch(url, opts);
  if (!r.ok) throw new Error(`${url}: ${r.status}`);
  return r.json();
}

function el(id) { return document.getElementById(id); }

function setSelect(selectEl, options, selected) {
  selectEl.innerHTML = '';
  for (const opt of options) {
    const o = document.createElement('option');
    o.value = opt.value;
    o.textContent = opt.label;
    if (opt.value === selected) o.selected = true;
    selectEl.appendChild(o);
  }
}

async function loadCatalogs() {
  const [tagsResp, metricsResp] = await Promise.all([j('/api/tags'), j('/api/metrics')]);
  state.tags = tagsResp.tags;
  state.metrics = metricsResp.metrics;
  state.regionRegistry = metricsResp.region_registry || {};
  state.regionOrder = metricsResp.region_order || Object.keys(state.regionRegistry);
  state.regionsOn = new Set(state.regionOrder.filter(r => state.regionRegistry[r]?.default_on));
  if (state.regionsOn.size < 2) state.regionsOn = new Set(state.regionOrder.slice(0, 2));

  const priority = ['last30y', 'last10y', 'last5y', 'last3y', 'last1y', 'sample_last30'];
  state.tag = priority.find(t => state.tags.includes(t)) || state.tags[0];

  setSelect(el('metric'), state.metrics.map(m => ({ value: m.key, label: m.label })), 'stay_outside_hours');
  renderRangePicker();
  renderRegionPicker();
  el('tag-badge').textContent = `dataset: ${state.tag}`;
}

function renderRangePicker() {
  const host = el('range-picker');
  host.innerHTML = '';
  const ordered = [
    ...RANGE_ORDER.filter(r => state.tags.includes(r.tag)),
    ...state.tags.filter(t => !RANGE_ORDER.some(r => r.tag === t)).map(t => ({ tag: t, label: t })),
  ];
  // Also render disabled placeholders for ranges that aren't on disk yet, so
  // viewers can see what's *coming*.
  const placeholders = RANGE_ORDER.filter(r => !state.tags.includes(r.tag));
  const allBtns = [...ordered, ...placeholders];
  allBtns.forEach(r => {
    const b = document.createElement('button');
    b.type = 'button';
    b.textContent = r.label;
    b.dataset.tag = r.tag;
    if (r.tag === state.tag) b.classList.add('active');
    if (!state.tags.includes(r.tag)) {
      b.disabled = true;
      b.title = 'Dataset not yet available on disk';
    } else {
      b.addEventListener('click', () => {
        if (state.tag === r.tag) return;
        state.tag = r.tag;
        host.querySelectorAll('button').forEach(x => x.classList.toggle('active', x.dataset.tag === r.tag));
        reload();
      });
    }
    host.appendChild(b);
  });
}

function renderRegionPicker() {
  const host = el('region-picker');
  host.innerHTML = '';
  state.regionOrder.forEach(region => {
    const reg = state.regionRegistry[region];
    if (!reg) return;
    const chip = document.createElement('button');
    chip.type = 'button';
    chip.className = 'region-chip';
    chip.style.setProperty('--chip-color', reg.color);
    chip.style.setProperty('--chip-halo', `${reg.color}33`);
    chip.style.setProperty('--chip-bg', `${reg.color}11`);
    chip.dataset.region = region;
    chip.innerHTML = `<span class="dot"></span>${escapeHtml(reg.label)}${reg.default_on ? '' : ' <span class="chip-mute">(tap to compare)</span>'}`;
    if (state.regionsOn.has(region)) chip.classList.add('active');
    chip.addEventListener('click', () => {
      if (state.regionsOn.has(region)) {
        if (state.regionsOn.size <= 1) return; // keep at least one
        state.regionsOn.delete(region);
      } else {
        state.regionsOn.add(region);
      }
      chip.classList.toggle('active');
      render();
    });
    host.appendChild(chip);
  });
}

const seriesCache = { key: null, data: null };
let seriesCtl = null;

async function loadSeries() {
  const tag = state.tag;
  const grain = el('grain').value;
  const metric = el('metric').value;
  const key = `${tag}|${grain}|${metric}`;
  if (seriesCtl) seriesCtl.abort();
  if (seriesCache.key === key) return true;
  const ctl = seriesCtl = new AbortController();
  el('tag-badge').textContent = `loading ${tag}/${grain}/${metric}…`;
  try {
    const data = await j(`/api/series?tag=${encodeURIComponent(tag)}&grain=${grain}&metric=${metric}`, { signal: ctl.signal });
    if (ctl !== seriesCtl) return false;
    seriesCache.key = key;
    seriesCache.data = data;
    return true;
  } catch (err) {
    if (err.name === 'AbortError' || ctl !== seriesCtl) return false;
    seriesCache.key = null;
    seriesCache.data = null;
    clearChart(el('chart'));
    el('chart').innerHTML = `<p class="chart-error">${escapeHtml("This metric isn't available for the selected range")}</p>`;
    el('tag-badge').textContent = `${tag} · ${grain} · unavailable`;
    return false;
  }
}

function render() {
  const data = seriesCache.data;
  if (!data) return;
  const [tag, grain, metric] = seriesCache.key.split('|');
  const chartEl = el('chart');
  if (chartEl.querySelector('.chart-error')) clearChart(chartEl);
  const visible = visibleRegions();
  renderChart(chartEl, buildTraces(data, visible, state.regionRegistry, grain), layoutFor(data, grain),
    (rawX) => {
      const [curTag, curGrain] = seriesCache.key.split('|');
      panel.open({
        tag: curTag, grain: curGrain, bucket: toBucket(rawX, curGrain),
        xLabel: String(rawX),
        metricLabel: data.metric_label,
        unit: data.unit,
      });
    });
  const visibleCounts = visible.filter(r => data.series[r]).reduce((sum, r) => sum + (data.series[r]?.x?.length || 0), 0);
  el('tag-badge').textContent = `${tag} · ${grain} · ${visible.length} counties · ${visibleCounts} points`;
  const model = buildTakeaway({
    series: data.series, visible, metricMeta: state.metrics.find(m => m.key === metric),
    registry: state.regionRegistry, grain,
  });
  const rangeDef = RANGE_ORDER.find(x => x.tag === tag);
  renderTakeaway(model, { text: el('takeaway-text'), aux: el('takeaway-aux'), host: el('takeaway') });
  renderHeroStats(model, el('hero-stats'), rangeDef ? rangeDef.label : tag);
}

async function reload() {
  if (await loadSeries()) render();
}

window.addEventListener('DOMContentLoaded', async () => {
  await loadCatalogs();
  panel = createDetailPanel({ root: el('detail'), fetchJson: j, getVisibleRegions: visibleRegions });
  el('grain').addEventListener('change', reload);
  el('metric').addEventListener('change', reload);
  await reload();
});
