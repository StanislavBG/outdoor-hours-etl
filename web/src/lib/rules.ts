// Single source of truth for formatting a profile rule (Rules card, thresholds strip, tooltips).
// No imports: node runs this directly (--experimental-strip-types) in tests.

export interface ProfileRule {
  temp_min_c: number; temp_max_c: number; temp_min_f: number; temp_max_f: number;
  uv_max: number; rain_max_mm_h: number;
  cloud_max_pct: number | null; humidity_max_pct: number | null; aqi_max: number | null;
}

export type RuleKey = 'daytime' | 'temp' | 'uv' | 'rain' | 'cloud' | 'humidity' | 'aqi';

export interface RuleItem {
  key: RuleKey;
  icon: string;
  name: string;
  value: string;
  sub: string;
  limited: boolean;
}

export function ruleItems(rule: ProfileRule, opts: { includeUnlimited: boolean }): RuleItem[] {
  const items: RuleItem[] = [
    { key: 'daytime', icon: '☀', name: 'Daytime', value: 'Sun is up', sub: 'Nighttime hours don’t count.', limited: true },
    { key: 'temp', icon: '🌡', name: 'Comfortable temp', value: `${rule.temp_min_f}°–${rule.temp_max_f}°F`, sub: `That’s ${rule.temp_min_c}°–${rule.temp_max_c}°C.`, limited: true },
    { key: 'uv', icon: '⛅', name: 'Safe UV', value: `Index ≤ ${rule.uv_max}`, sub: 'Above that and dermatologists say cover up.', limited: true },
    { key: 'rain', icon: '☂', name: 'Not raining', value: `≤ ${rule.rain_max_mm_h} mm/hr`, sub: 'Light drizzle is OK — a downpour isn’t.', limited: true },
    { key: 'cloud', icon: '☁', name: 'Not overcast', value: rule.cloud_max_pct != null ? `Cloud ≤ ${rule.cloud_max_pct}%` : 'No limit', sub: 'Socked-in skies kill the vibe even when it’s warm.', limited: rule.cloud_max_pct != null },
    { key: 'humidity', icon: '💧', name: 'Not muggy', value: rule.humidity_max_pct != null ? `Humidity ≤ ${rule.humidity_max_pct}%` : 'No limit', sub: 'Above this, sweat can’t evaporate and the air feels heavy.', limited: rule.humidity_max_pct != null },
    { key: 'aqi', icon: '🌫', name: 'Clean air', value: rule.aqi_max != null ? `US AQI ≤ ${rule.aqi_max}` : 'No limit', sub: 'Pre-Aug-2022 hours don’t fail this rule (no AQ data).', limited: rule.aqi_max != null },
  ];
  return opts.includeUnlimited ? items : items.filter(i => i.limited);
}

export function ruleSummary(rule: ProfileRule): string {
  const parts = [
    `Temp ${rule.temp_min_f}–${rule.temp_max_f}°F`,
    `UV ≤ ${rule.uv_max}`,
    `Rain ≤ ${rule.rain_max_mm_h} mm/hr`,
  ];
  if (rule.cloud_max_pct != null) parts.push(`Cloud ≤ ${rule.cloud_max_pct}%`);
  if (rule.humidity_max_pct != null) parts.push(`Humidity ≤ ${rule.humidity_max_pct}%`);
  if (rule.aqi_max != null) parts.push(`AQI ≤ ${rule.aqi_max}`);
  return parts.join(' · ');
}
