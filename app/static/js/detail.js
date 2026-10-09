// Drill-down detail panel. Pure rendering is exported for tests; DOM work
// happens only inside createDetailPanel.
import { escapeHtml, prettyBucket, fmtCell, cellClass } from './format.js';

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
 * @param rows      list of {_x, <region>: {col: val, n_points?}, <shared_key>: val}
 * @param registry  {region_key: {short, color, ...}}
 * @param order     [region_key, ...] (order to render)
 * @param drillOf   optional (row) => {grain, bucket, label} | null; makes rows drillable
 */
export function renderPairedTable(columns, rows, registry, order, drillOf = null) {
  const regionOrder = order || Object.keys(registry || {});
  const reg = registry || {};
  const paired   = columns.filter(c => c.paired);
  const shared   = columns.filter(c => !c.paired);
  const leading  = paired.filter(c => c.leading);
  const trailing = paired.filter(c => !c.leading);
  const ordered = [...shared, ...leading, ...trailing];

  // Two-tier header: top row groups region columns; bottom row is region names.
  let topHead = '';
  let bottomHead = '';
  ordered.forEach(c => {
    if (!c.paired) {
      topHead += `<th rowspan="2" class="shared-hdr">${escapeHtml(c.label)}</th>`;
      return;
    }
    const groupCls = c.leading ? 'hdr-lead' : '';
    topHead += `<th colspan="${regionOrder.length}" class="group-hdr ${groupCls}"><span class="group-title">${escapeHtml(c.label)}</span></th>`;
    regionOrder.forEach(r => {
      const short = reg[r]?.short ?? r;
      const color = escapeHtml(reg[r]?.color || '#888');
      bottomHead += `<th class="col-region ${c.leading ? 'hdr-lead-sub' : ''}"><span class="dot" style="--region-color:${color}"></span>${escapeHtml(short)}</th>`;
    });
  });
  const head = `<tr>${topHead}</tr><tr>${bottomHead}</tr>`;

  let drillable = false;
  const body = rows.map(r => {
    const winners = {};
    leading.forEach(c => { winners[c.key] = leadingWinner(r, c.key, regionOrder, true); });
    const cells = ordered.map(c => {
      if (!c.paired) {
        const raw = r[c.key] ?? r._x;
        return `<td class="shared ${cellClass(c.fmt)}">${fmtCell(raw, c.fmt)}</td>`;
      }
      return regionOrder.map(region => {
        const cell = r[region];
        const winCls = c.leading && winners[c.key] === region ? ' leader' : '';
        const leadCls = c.leading ? ' lead-cell' : '';
        const text = fmtCell(cell?.[c.key], c.fmt, cell?.n_points ?? 3);
        return `<td class="${cellClass(c.fmt)} col-region${winCls}${leadCls}">${text}</td>`;
      }).join('');
    }).join('');
    const d = drillOf ? drillOf(r) : null;
    if (!d) return `<tr>${cells}</tr>`;
    drillable = true;
    return `<tr data-grain="${escapeHtml(d.grain)}" data-bucket="${escapeHtml(d.bucket)}" data-label="${escapeHtml(d.label)}">${cells}</tr>`;
  }).join('');

  return `<table class="paired-table"><thead>${head}</thead><tbody${drillable ? ' class="drillable"' : ''}>${body}</tbody></table>`;
}

function renderBreadcrumb(stack) {
  const crumbs = stack.map((s, i) => {
    const last = i === stack.length - 1;
    const label = `${escapeHtml(s.xLabel)}<span class="crumb-grain"> · ${escapeHtml(s.grain)}</span>`;
    return last
      ? `<span class="crumb crumb-here">${label}</span>`
      : `<button class="crumb crumb-link" data-i="${i}">${label}</button>`;
  }).join('<span class="crumb-sep">›</span>');
  return `<nav class="detail-crumbs">${crumbs}</nav>`;
}

// What a click on a row drills TO: the current detail_grain is the bucket
// being clicked, and the endpoint returns a finer breakdown.
function drillTarget(detailGrain, row) {
  if (detailGrain !== 'daily' && detailGrain !== 'monthly') return null;
  const xStr = String(row._x);
  if (detailGrain === 'daily') {
    return { grain: 'daily', bucket: xStr.slice(0, 10), label: prettyBucket(xStr, 'daily') };
  }
  // monthly: _x is a "YYYY-MM" label → use as month_start
  const bucket = `${xStr}-01`;
  return { grain: 'monthly', bucket, label: prettyBucket(bucket, 'monthly') };
}

function hintHtml(d) {
  const n = Object.keys(d.regions || {}).length || (d.region_order || []).length;
  if (d.detail_grain === 'hourly') {
    return `<p class="detail-hint">${escapeHtml(d.n_rows)} hourly rows. <strong>Stay-out</strong> = how many of the sample points in each region passed <em>all four</em> rules that hour. The columns to the right show the <em>reason</em> — daytime, temperature, UV, rain — so you can see which rule killed the hour. Winner highlighted per row.</p>`;
  }
  const canDrill = d.detail_grain === 'daily' || d.detail_grain === 'monthly';
  const drill = canDrill ? ` <strong>Click any row</strong> to drop down to the ${d.detail_grain === 'daily' ? 'hour-by-hour' : 'day-by-day'} view.` : '';
  return `<p class="detail-hint">${escapeHtml(d.n_rows)} ${escapeHtml(d.detail_grain)} rows, ${escapeHtml(n)} ${n === 1 ? 'region' : 'regions'} side by side. Classification columns lead; winner starred.${drill}</p>`;
}

export function createDetailPanel({ root, fetchJson, getVisibleRegions }) {
  const $ = (id) => root.querySelector(`#${id}`);
  const body = $('detail-body');
  let stack = [];       // [{grain, bucket, xLabel}]
  let ctx = null;       // {tag, metricLabel, unit}

  async function load() {
    if (!stack.length || !ctx) return;
    const current = stack[stack.length - 1];
    const { tag, metricLabel, unit } = ctx;
    body.innerHTML = '<p class="detail-empty">Loading…</p>';
    $('detail-title').textContent = `${current.xLabel} — side-by-side`;
    $('detail-sub').textContent = `Drill by ${metricLabel ? metricLabel.toLowerCase() : 'metric'}${unit ? ' · ' + unit + ' where applicable' : ''}`;
    const crumbs = renderBreadcrumb(stack);
    try {
      const params = new URLSearchParams({ tag, grain: current.grain, bucket: current.bucket });
      const visible = getVisibleRegions();
      if (visible && visible.length) params.set('regions', visible.join(','));
      const d = await fetchJson(`/api/detail?${params}`);
      if (!d.rows.length) {
        body.innerHTML = crumbs + '<p class="detail-empty">No underlying rows for this point.</p>';
        return;
      }
      body.innerHTML = crumbs + hintHtml(d)
        + renderPairedTable(d.columns, d.rows, d.region_registry, d.region_order, (r) => drillTarget(d.detail_grain, r));
    } catch (err) {
      body.innerHTML = crumbs + `<p class="detail-empty">Failed to load detail: ${escapeHtml(err.message)}</p>`;
    }
  }

  function close() {
    root.hidden = true;
    root.classList.remove('fullscreen');
    document.body.classList.remove('detail-open');
  }

  function toggleFullscreen() {
    const on = root.classList.toggle('fullscreen');
    document.body.classList.toggle('detail-open', on);
    $('detail-fs').textContent = on ? '⤡ Exit full screen' : '⤢ Full screen';
  }

  async function open({ tag, grain, bucket, xLabel, metricLabel, unit }) {
    stack = [{ grain, bucket, xLabel }];
    ctx = { tag, metricLabel, unit };
    root.hidden = false;
    await load();
  }

  // One delegated listener for breadcrumbs and drillable rows.
  body.addEventListener('click', (e) => {
    const crumb = e.target.closest('.crumb-link');
    if (crumb) {
      stack = stack.slice(0, Number(crumb.dataset.i) + 1);
      load();
      return;
    }
    const tr = e.target.closest('tr[data-bucket]');
    if (tr) {
      stack.push({ grain: tr.dataset.grain, bucket: tr.dataset.bucket, xLabel: tr.dataset.label });
      load();
    }
  });
  $('detail-close').addEventListener('click', close);
  $('detail-fs').addEventListener('click', toggleFullscreen);
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape' && !root.hidden) close();
  });

  return { open, close, toggleFullscreen };
}
