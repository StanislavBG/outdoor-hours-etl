// Chart building. buildTraces/layoutFor are pure; Plotly is only touched inside
// renderChart/clearChart so the module imports cleanly under node.
import { escapeHtml } from './format.js';

export function layoutFor(meta, grain) {
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

export function buildTraces(data, visible, registry, grain) {
  return visible
    .filter(region => data.series[region])
    .map(region => {
      const s = data.series[region];
      const color = registry[region]?.color || '#888';
      return {
        x: s.x, y: s.y, name: s.label, type: 'scatter', mode: 'lines+markers',
        marker: { size: grain === 'yearly' ? 11 : 7, color, line: { width: 1, color: 'white' } },
        line: { width: 3, color },
        meta: region,
        hovertemplate: `<b>${escapeHtml(s.label)}</b><br>%{x}<br>${escapeHtml(data.metric_label)}: %{y:.2f} ${escapeHtml(data.unit)}<br><i>(click to drill in)</i><extra></extra>`,
      };
    });
}

const bound = new WeakSet();
// The click handler is bound once per element; it always calls the latest callback.
const handlers = new WeakMap();

export function renderChart(el, traces, layout, onPointClick) {
  handlers.set(el, onPointClick);
  Plotly.react(el, traces, layout, { responsive: true, displaylogo: false,
    modeBarButtonsToRemove: ['lasso2d', 'select2d'] });
  if (bound.has(el)) return;
  bound.add(el);
  el.on('plotly_click', (ev) => {
    if (!ev.points || !ev.points.length) return;
    const p = ev.points[0];
    handlers.get(el)?.(p.data.x[p.pointIndex], p);
  });
}

// Drop any plot (and its listeners) so the element can show plain content.
export function clearChart(el) {
  if (bound.has(el)) {
    Plotly.purge(el);
    bound.delete(el);
  }
  el.innerHTML = '';
}
