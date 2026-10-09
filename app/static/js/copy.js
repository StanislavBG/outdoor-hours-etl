// Pure page copy derived from /api/metrics: no document access.

const has = v => v !== null && v !== undefined;

export function heroRegions(registry, order) {
  const reg = registry || {};
  return (order || [])
    .filter(key => reg[key]?.default_on)
    .map(key => ({ label: reg[key].label || key, color: reg[key].color || '#888' }));
}

// One entry per non-null rule: {cls, icon, name, value, sub}.
export function rulesFromProfile(rule) {
  const r = rule || {};
  const out = [{
    cls: 'rule-sun', icon: '☀', name: 'Daytime',
    value: 'Sun is up', sub: 'Nighttime hours don’t count.',
  }];
  if (has(r.temp_min_f) && has(r.temp_max_f)) {
    out.push({
      cls: 'rule-temp', icon: '\u{1F321}', name: 'Comfortable temp',
      value: `${r.temp_min_f}°–${r.temp_max_f}°F`,
      sub: `That’s ${r.temp_min_c}°–${r.temp_max_c}°C — not too cold, not too hot.`,
    });
  }
  if (has(r.uv_max)) {
    out.push({
      cls: 'rule-uv', icon: '⛅', name: 'Safe UV',
      value: `Index ≤ ${r.uv_max}`, sub: `Above ${r.uv_max} and dermatologists say cover up.`,
    });
  }
  if (has(r.rain_max_mm_h)) {
    out.push({
      cls: 'rule-rain', icon: '☂', name: 'Barely raining',
      value: `≤ ${r.rain_max_mm_h} mm/hr`,
      sub: 'Light drizzle is OK — a real downpour isn’t.',
    });
  }
  if (has(r.cloud_max_pct)) {
    out.push({
      cls: 'rule-cloud', icon: '☁', name: 'Not overcast',
      value: `Cloud ≤ ${r.cloud_max_pct}%`, sub: 'Some cloud is fine; a solid grey sky isn’t.',
    });
  }
  if (has(r.humidity_max_pct)) {
    out.push({
      cls: 'rule-hum', icon: '\u{1F4A7}', name: 'Not muggy',
      value: `Humidity ≤ ${r.humidity_max_pct}%`, sub: 'Keeps the air from feeling heavy.',
    });
  }
  if (has(r.aqi_max)) {
    out.push({
      cls: 'rule-aqi', icon: '\u{1F32C}', name: 'Clean air',
      value: `AQI ≤ ${r.aqi_max}`, sub: 'Air quality stays in the good-to-moderate range.',
    });
  }
  return out;
}
