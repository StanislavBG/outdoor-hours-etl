import { escapeHtml, fmtValue, prettyBucket, toBucket, fmtCell, cellClass } from './js/format.js';
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

function regionColor(key) { return state.regionRegistry[key]?.color || '#888'; }
function regionInk(key)   { return state.regionRegistry[key]?.ink   || '#555'; }
function regionLabel(key) { return state.regionRegistry[key]?.label || key; }
function regionShort(key) { return state.regionRegistry[key]?.short || key.slice(0, 3).toUpperCase(); }

function visibleRegions() {
  return state.regionOrder.filter(r => state.regionsOn.has(r));
}

async function j(url) {
  const r = await fetch(url);
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
        refresh();
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
      refresh();
    });
    host.appendChild(chip);
  });
}

function layoutFor(meta, grain) {
  const grainLabel = { daily: 'Day', monthly: 'Month', yearly: 'Year' }[grain];
  const inter = 'Inter, -apple-system, BlinkMacSystemFont, Segoe UI, Roboto, sans-serif';
  return {
    title: {
      text: `${escapeHtml(meta.metric_label)}  <span style="color:#6b7388;font-weight:500">per ${grainLabel.toLowerCase()}</span>`,
      font: { family: inter, size: 26, color: '#121726', weight: 800 },
      x: 0.02, xanchor: 'left', y: 0.96,
    },
    font: { family: inter, color: '#39415a', size: 15 },
    xaxis: {
      title: { text: grain === 'yearly' ? 'Year' : 'Local date', font: { size: 15, color: '#6b7388' } },
      type: grain === 'yearly' ? 'linear' : 'date',
      showgrid: true, gridcolor: '#eef0f5',
      linecolor: '#c9cedb', tickcolor: '#c9cedb',
      tickfont: { size: 14 },
    },
    yaxis: {
      title: { text: `${meta.metric_label} (${meta.unit})`, font: { size: 15, color: '#6b7388' } },
      showgrid: true, gridcolor: '#eef0f5',
      zerolinecolor: '#e3e6ef',
      linecolor: '#c9cedb', tickcolor: '#c9cedb',
      tickfont: { size: 14 },
      rangemode: meta.metric === 'stay_outside_hours' ? 'tozero' : undefined,
    },
    hovermode: 'x unified',
    hoverlabel: { bgcolor: '#121726', bordercolor: '#121726', font: { color: 'white', family: inter, size: 15 } },
    legend: { orientation: 'h', y: -0.18, font: { size: 15, color: '#121726' }, bgcolor: 'rgba(0,0,0,0)' },
    margin: { l: 80, r: 32, t: 80, b: 80 },
    plot_bgcolor: 'white',
    paper_bgcolor: 'white',
    annotations: [
      {
        xref: 'paper', yref: 'paper', x: 0.015, y: 1.12, xanchor: 'left', yanchor: 'bottom',
        text: `<span style="color:#6b7388">${escapeHtml(meta.tag)}</span>  ·  <span style="color:#6b7388">${escapeHtml(grain)}</span>  ·  <code style="color:#4055f1">${escapeHtml(meta.metric)}</code>`,
        showarrow: false, font: { size: 11, family: inter },
      },
    ],
  };
}

async function refresh() {
  const tag = state.tag;
  const grain = el('grain').value;
  const metric = el('metric').value;
  el('tag-badge').textContent = `loading ${tag}/${grain}/${metric}…`;
  const data = await j(`/api/series?tag=${encodeURIComponent(tag)}&grain=${grain}&metric=${metric}`);

  const visible = visibleRegions();
  const traces = visible
    .filter(region => data.series[region])
    .map(region => {
      const s = data.series[region];
      return {
        x: s.x, y: s.y, name: s.label, type: 'scatter', mode: 'lines+markers',
        marker: { size: grain === 'yearly' ? 11 : 7, color: regionColor(region), line: { width: 1, color: 'white' } },
        line: { width: 3, color: regionColor(region) },
        meta: region,
        hovertemplate: `<b>${escapeHtml(s.label)}</b><br>%{x}<br>${escapeHtml(data.metric_label)}: %{y:.2f} ${escapeHtml(data.unit)}<br><i>(click to drill in)</i><extra></extra>`,
      };
    });

  Plotly.newPlot('chart', traces, layoutFor(data, grain), { responsive: true, displaylogo: false,
    modeBarButtonsToRemove: ['lasso2d', 'select2d'] });
  const visibleCounts = visible.filter(r => data.series[r]).reduce((sum, r) => sum + (data.series[r]?.x?.length || 0), 0);
  el('tag-badge').textContent = `${tag} · ${grain} · ${visible.length} counties · ${visibleCounts} points`;
  const model = buildTakeaway({
    series: data.series, visible, metricMeta: state.metrics.find(m => m.key === metric),
    registry: state.regionRegistry, grain,
  });
  const rangeDef = RANGE_ORDER.find(x => x.tag === state.tag);
  renderTakeaway(model, { text: el('takeaway-text'), aux: el('takeaway-aux'), host: el('takeaway') });
  renderHeroStats(model, el('hero-stats'), rangeDef ? rangeDef.label : state.tag);

  const chartEl = el('chart');
  chartEl.removeAllListeners && chartEl.removeAllListeners('plotly_click');
  chartEl.on('plotly_click', (ev) => {
    if (!ev.points || !ev.points.length) return;
    const p = ev.points[0];
    const rawX = p.data.x[p.pointIndex];
    const bucket = toBucket(rawX, grain);
    openDetail({
      tag, grain, bucket,
      xLabel: String(rawX),
      metricLabel: data.metric_label,
      unit: data.unit,
    });
  });
}

// ---- detail panel ------------------------------------------------------

const REGION_ORDER_DEFAULT = ['santa_clara_ca', 'eastside_king_wa'];
const REGION_CLASS = { santa_clara_ca: 'col-scc', eastside_king_wa: 'col-king' };
const REGION_SHORT = { santa_clara_ca: 'SCC', eastside_king_wa: 'WA' };

// Winner highlighting for the leading classification metric.
function leadingWinner(row, key, regionOrder, higherIsBetter = true) {
  const vals = regionOrder.map(r => row[r]?.[key]).filter(v => v != null && Number.isFinite(Number(v)));
  if (vals.length < 2) return null;
  const best = higherIsBetter ? Math.max(...vals) : Math.min(...vals);
  return regionOrder.find(r => Number(row[r]?.[key]) === best);
}

/**
 * Render the side-by-side detail table.
 * @param columns   list of {key, label, fmt, paired, leading}
 * @param rows      list of {_x, <region>: {col: val, ...}, <shared_key>: val}
 * @param regions   {region_key: friendly_label}
 * @param order     [region_key, ...] (order to render)
 */
function renderPairedTable(columns, rows, regions, order) {
  const regionOrder = order || REGION_ORDER_DEFAULT;
  const paired   = columns.filter(c => c.paired);
  const shared   = columns.filter(c => !c.paired);
  const leading  = paired.filter(c => c.leading);
  const trailing = paired.filter(c => !c.leading);
  const ordered = [...shared, ...leading, ...trailing];

  // Two-tier header: top row groups region columns; bottom row is metric names.
  let topHead = '';
  let bottomHead = '';
  ordered.forEach((c, i) => {
    if (!c.paired) {
      topHead += `<th rowspan="2" class="shared-hdr">${escapeHtml(c.label)}</th>`;
      return;
    }
    // Classification leaders get a highlighted top-group (both regions under one banner).
    const groupCls = c.leading ? 'hdr-lead' : '';
    topHead += `<th colspan="${regionOrder.length}" class="group-hdr ${groupCls}"><span class="group-title">${escapeHtml(c.label)}</span></th>`;
    regionOrder.forEach(r => {
      bottomHead += `<th class="${REGION_CLASS[r]} ${c.leading ? 'hdr-lead-sub' : ''}"><span class="dot dot-${r === 'santa_clara_ca' ? 'scc' : 'king'}"></span>${escapeHtml(REGION_SHORT[r] ?? r)}</th>`;
    });
  });

  const head = `<tr>${topHead}</tr><tr>${bottomHead}</tr>`;

  // Rows: determine a winner per leading metric for subtle emphasis.
  const body = rows.map(r => {
    const winners = {};
    leading.forEach(c => {
      // For all our leading metrics (stay_outside_*, pct_daytime_outside), higher is better.
      winners[c.key] = leadingWinner(r, c.key, regionOrder, true);
    });
    const cells = ordered.map(c => {
      if (!c.paired) {
        const raw = r[c.key] ?? r._x;
        return `<td class="shared ${cellClass(c.fmt)}">${fmtCell(raw, c.fmt)}</td>`;
      }
      return regionOrder.map(region => {
        const raw = r[region]?.[c.key];
        const isLead = c.leading;
        const winCls = isLead && winners[c.key] === region ? ' leader' : '';
        const leadCls = isLead ? ' lead-cell' : '';
        return `<td class="${cellClass(c.fmt)} ${REGION_CLASS[region]}${winCls}${leadCls}">${fmtCell(raw, c.fmt)}</td>`;
      }).join('');
    }).join('');
    return `<tr>${cells}</tr>`;
  }).join('');

  return `<table class="paired-table"><thead>${head}</thead><tbody>${body}</tbody></table>`;
}

// Drill stack: each entry = {grain, bucket, xLabel}. Breadcrumbs from the stack
// let the user hop back up without closing the panel.
let drillStack = [];
let drillCtx = null; // {tag, metricLabel, unit}

async function openDetail({ tag, grain, bucket, xLabel, metricLabel, unit }) {
  drillStack = [{ grain, bucket, xLabel }];
  drillCtx = { tag, metricLabel, unit };
  el('detail').hidden = false;
  await loadDetailLevel();
}

async function drillFurther(newGrain, newBucket, newXLabel) {
  drillStack.push({ grain: newGrain, bucket: newBucket, xLabel: newXLabel });
  await loadDetailLevel();
}

async function drillUp(toIndex) {
  drillStack = drillStack.slice(0, toIndex + 1);
  await loadDetailLevel();
}

function renderBreadcrumb() {
  const crumbs = drillStack.map((s, i) => {
    const last = i === drillStack.length - 1;
    const label = `${escapeHtml(s.xLabel)}<span class="crumb-grain"> · ${escapeHtml(s.grain)}</span>`;
    return last
      ? `<span class="crumb crumb-here">${label}</span>`
      : `<button class="crumb crumb-link" data-i="${i}">${label}</button>`;
  }).join('<span class="crumb-sep">›</span>');
  return `<nav class="detail-crumbs">${crumbs}</nav>`;
}

async function loadDetailLevel() {
  if (!drillStack.length || !drillCtx) return;
  const current = drillStack[drillStack.length - 1];
  const { tag, metricLabel, unit } = drillCtx;
  el('detail-body').innerHTML = '<p class="detail-empty">Loading…</p>';
  el('detail-title').textContent = `${current.xLabel} — side-by-side`;
  el('detail-sub').textContent = `Drill by ${metricLabel ? metricLabel.toLowerCase() : 'metric'}${unit ? ' · ' + unit + ' where applicable' : ''}`;

  try {
    const qs = new URLSearchParams({ tag, grain: current.grain, bucket: current.bucket }).toString();
    const d = await j(`/api/detail?${qs}`);
    if (!d.rows.length) {
      el('detail-body').innerHTML = renderBreadcrumb() + '<p class="detail-empty">No underlying rows for this point.</p>';
      wireCrumbs();
      return;
    }
    let note;
    if (d.detail_grain === 'hourly') {
      note = `<p class="detail-hint">${escapeHtml(d.n_rows)} hourly rows. <strong>Stay-out</strong> = how many of the 3 sample neighborhoods passed <em>all four</em> rules that hour. The columns to the right show the <em>reason</em> — daytime, temperature, UV, rain — so you can see which rule killed the hour. Winner highlighted per row.</p>`;
    } else {
      const canDrill = d.detail_grain === 'daily' || d.detail_grain === 'monthly';
      note = `<p class="detail-hint">${escapeHtml(d.n_rows)} ${escapeHtml(d.detail_grain)} rows, both counties side by side. Classification columns lead; winner starred.${canDrill ? ' <strong>Click any row</strong> to drop down to the ' + (d.detail_grain === 'daily' ? 'hour-by-hour' : 'day-by-day') + ' view.' : ''}</p>`;
    }
    el('detail-body').innerHTML = renderBreadcrumb() + note + renderPairedTable(d.columns, d.rows, d.regions, d.region_order);

    wireCrumbs();
    wireRowDrill(d);
  } catch (err) {
    el('detail-body').innerHTML = renderBreadcrumb() + `<p class="detail-empty">Failed to load detail: ${escapeHtml(err.message)}</p>`;
    wireCrumbs();
  }
}

function wireCrumbs() {
  el('detail-body').querySelectorAll('.crumb-link').forEach(btn => {
    btn.addEventListener('click', () => drillUp(Number(btn.dataset.i)));
  });
}

function wireRowDrill(d) {
  // Attach data attributes to <tr> and listen for row clicks, only when a
  // deeper drill makes sense (daily → hourly, monthly → daily).
  if (d.detail_grain !== 'daily' && d.detail_grain !== 'monthly') return;
  const tbody = el('detail-body').querySelector('.paired-table tbody');
  if (!tbody) return;
  tbody.classList.add('drillable');
  const rows = tbody.querySelectorAll('tr');
  d.rows.forEach((r, i) => {
    const tr = rows[i];
    if (!tr) return;
    const rawX = r._x;
    const xStr = typeof rawX === 'string' ? rawX : String(rawX);
    // What grain do we drill TO? The current detail_grain IS the bucket we're
    // clicking; a click's grain parameter becomes that detail_grain, and the
    // endpoint returns a finer breakdown.
    const nextGrain = d.detail_grain; // 'daily' or 'monthly'
    let nextBucket;
    let nextLabel;
    if (nextGrain === 'daily') {
      nextBucket = xStr.slice(0, 10);
      nextLabel = prettyBucket(xStr, 'daily');
    } else { // monthly
      // r._x for monthly is a "YYYY-MM" label from month_label → use as month_start
      nextBucket = `${xStr}-01`;
      nextLabel = prettyBucket(nextBucket, 'monthly');
    }
    tr.addEventListener('click', () => drillFurther(nextGrain, nextBucket, nextLabel));
  });
}

function closeDetail() {
  el('detail').hidden = true;
  el('detail').classList.remove('fullscreen');
  document.body.classList.remove('detail-open');
}

function toggleFullscreen() {
  const p = el('detail');
  const on = p.classList.toggle('fullscreen');
  document.body.classList.toggle('detail-open', on);
  el('detail-fs').textContent = on ? '⤡ Exit full screen' : '⤢ Full screen';
}

window.addEventListener('DOMContentLoaded', async () => {
  await loadCatalogs();
  el('grain').addEventListener('change', refresh);
  el('metric').addEventListener('change', refresh);
  el('detail-close').addEventListener('click', closeDetail);
  el('detail-fs').addEventListener('click', toggleFullscreen);
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape' && !el('detail').hidden) closeDetail();
  });
  await refresh();
});
