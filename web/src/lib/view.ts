// Single source of truth for the page's default view and its URL round-trip.
// No imports: node runs this directly (--experimental-strip-types) in tests.

export interface RangeOption { tag: string; label: string; long: string; }

export const RANGE_ORDER: RangeOption[] = [
  { tag: 'last30y', label: '30 yrs',  long: 'Last 30 years' },
  { tag: 'last10y', label: '10 yrs',  long: 'Last 10 years' },
  { tag: 'last5y',  label: '5 yrs',   long: 'Last 5 years' },
  { tag: 'last3y',  label: '3 yrs',   long: 'Last 3 years' },
  { tag: 'last1y',  label: '1 yr',    long: 'Last year' },
  { tag: 'last1m',  label: '30 days', long: 'Last 30 days' },
];

export interface ViewDefaults {
  tag: string;
  grain: string;
  metric: string;
  profile: string;
  yoy: boolean;
}

export const DEFAULT_VIEW: ViewDefaults = {
  tag: 'last1m',
  grain: 'daily',
  metric: 'stay_outside_hours',
  profile: 'goldilocks',
  yoy: false,
};

export function rangeLabel(tag: string): string {
  return RANGE_ORDER.find(r => r.tag === tag)?.label ?? tag;
}

export function rangeLongLabel(tag: string): string {
  return RANGE_ORDER.find(r => r.tag === tag)?.long ?? tag;
}

export interface InitialView extends ViewDefaults {
  profileFromUrl: boolean;
  regions: string[] | null;
}

export function readInitialView(get: (k: string) => string | null): InitialView {
  const profile = get('profile');
  const regions = get('regions');
  return {
    tag: get('tag') || DEFAULT_VIEW.tag,
    grain: get('grain') || DEFAULT_VIEW.grain,
    metric: get('metric') || DEFAULT_VIEW.metric,
    profile: profile || DEFAULT_VIEW.profile,
    profileFromUrl: !!profile,
    regions: regions ? regions.split(',').filter(Boolean) : null,
    yoy: get('yoy') === '1',
  };
}

export function viewToParams(
  view: { tag: string; grain: string; metric: string; profile: string; yoy: boolean },
  defaults: ViewDefaults,
): Record<string, string> {
  const out: Record<string, string> = {};
  if (view.tag !== defaults.tag) out.tag = view.tag;
  if (view.grain !== defaults.grain) out.grain = view.grain;
  if (view.metric !== defaults.metric) out.metric = view.metric;
  if (view.profile !== defaults.profile) out.profile = view.profile;
  if (view.yoy) out.yoy = '1';
  return out;
}
