export type FlowProps = Record<string, unknown>;
export type TrackFn = (name: string, props: FlowProps) => void;

const FLOW_NAME_RE = /^[a-z0-9][a-z0-9-]{0,39}$/;

export const isFlowName = (s: string): boolean => FLOW_NAME_RE.test(s);

/** Wraps a host-kit-style `track` into trackFlow(flow, step, props?). Invalid names are dropped silently. */
export function makeTrackFlow(trackFn: TrackFn) {
  return (flow: string, step: string, props?: FlowProps): void => {
    if (!isFlowName(flow) || !isFlowName(step)) return;
    trackFn(`${flow}.${step}`, { ...props, flow, step });
  };
}
