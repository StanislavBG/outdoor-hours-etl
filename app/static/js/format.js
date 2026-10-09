// Pure formatting helpers. No DOM access: safe to unit-test under node.

const HTML_ESCAPES = { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' };

export function escapeHtml(s) {
  return s == null ? '' : String(s).replace(/[&<>"']/g, c => HTML_ESCAPES[c]);
}

export function fmtValue(v, unit) {
  if (v == null) return '—';
  const abs = Math.abs(v);
  const digits = abs >= 1000 ? 0 : abs >= 100 ? 0 : abs >= 10 ? 1 : 2;
  return `${v.toLocaleString(undefined, { minimumFractionDigits: digits, maximumFractionDigits: digits })} ${unit || ''}`.trim();
}

export function prettyBucket(x, grain) {
  if (grain === 'yearly') return String(x);
  // ISO 2025-03-29 → "Mar 29, 2025" (daily) or "Mar 2025" (monthly)
  const m = String(x).match(/^(\d{4})-(\d{2})(?:-(\d{2}))?/);
  if (!m) return String(x);
  const year = +m[1], month = +m[2] - 1, day = m[3] ? +m[3] : null;
  const monthNames = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
  return day ? `${monthNames[month]} ${day}, ${year}` : `${monthNames[month]} ${year}`;
}

export function toBucket(x, grain) {
  // Values come from data.x (strings for daily/monthly ISO, ints for yearly).
  if (grain === 'yearly') return String(parseInt(x, 10));
  // ISO date strings like "2026-03-29" or "2026-03-01" pass through.
  return String(x).slice(0, 10);
}

const FMT = {
  num0: (v) => v == null ? '' : Number(v).toFixed(0),
  num1: (v) => v == null ? '' : Number(v).toFixed(1),
  num2: (v) => v == null ? '' : Number(v).toFixed(2),
  time: (v) => {
    if (v == null) return '';
    const m = String(v).match(/T(\d{2}:\d{2})/);
    return m ? m[1] : String(v);
  },
  bool: (v) => {
    if (v == null || v === '') return '';
    const n = Number(v);
    return `<span class="${n ? 'yes' : 'no'}">${n ? '✓' : '✗'}</span>`;
  },
  // "N / 3" score with color hint — used for hourly stay_outside_pts (0..3).
  pts: (v, max = 3) => {
    if (v == null) return '';
    const n = Number(v);
    const cls = n === 0 ? 'no' : n === max ? 'yes' : 'partial';
    return `<span class="${cls}">${n}/${max}</span>`;
  },
};

export function fmtCell(val, fmt) {
  if (fmt === 'bool') return FMT.bool(val);
  if (fmt === 'pts')  return FMT.pts(val);
  if (fmt && FMT[fmt]) return FMT[fmt](val);
  return val == null ? '' : String(val);
}

export function cellClass(fmt) {
  if (fmt === 'bool' || fmt === 'pts') return 'bool';
  if (fmt && fmt.startsWith('num')) return 'num';
  return '';
}
