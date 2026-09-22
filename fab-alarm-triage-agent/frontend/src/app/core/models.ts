/** DTOs mirroring the backend's Pydantic schemas.
 *
 * Kept deliberately narrow: the backend's alarm rows also carry ground-truth columns for
 * the eval harness, and those must never reach this app. Typing only the fields the API
 * actually returns means a leak would show up as a type error rather than quietly
 * rendering the answer on screen.
 */

export type Action = 'hold_lot' | 'continue' | 'escalate';
export type Severity = 'low' | 'medium' | 'high' | 'critical';
export type AlarmStatus = 'open' | 'triaged' | 'closed';
export type RunStatus = 'running' | 'awaiting_review' | 'completed' | 'failed';
export type DispositionStatus = 'pending' | 'approved' | 'edited' | 'rejected';
export type ReviewDecision = 'approve' | 'edit' | 'reject';

export interface Alarm {
  id: number;
  alarm_code: string;
  severity: Severity;
  message: string;
  raised_at: string;
  status: AlarmStatus;
  tool_id: string;
  chamber: string;
  lot_id: string | null;
  run_id: number | null;
}

export interface SensorPoint {
  run_id: number;
  started_at: string;
  value: number;
  z_score: number;
  out_of_limit: boolean;
}

export interface SignalTrace {
  signal_key: string;
  label: string;
  unit: string;
  lcl: number;
  ucl: number;
  current: SensorPoint;
  history: SensorPoint[];
}

export interface EquipmentState {
  id: number;
  tool_id: string;
  chamber: string;
  tool_type: string;
  status: string;
  as_of: string;
  last_pm_at: string | null;
  last_pm_by: string | null;
  pm_interval_days: number;
  days_since_pm: number | null;
  pm_overdue: boolean;
  pm_overdue_by_days: number;
  alarms_last_30d: number;
  open_alarms: number;
}

export interface Lot {
  id: number;
  lot_id: string;
  product: string;
  route_step: string;
  wafer_count: number;
  priority: string;
  status: string;
  started_at: string;
}

export interface AlarmDetail extends Alarm {
  equipment: EquipmentState;
  lot: Lot | null;
  recipe_id: number | null;
  recipe_name: string | null;
  out_of_limit: SignalTrace[];
}

export interface Evidence {
  source: string;
  ref: string;
  detail: string;
}

export interface Disposition {
  id: number;
  alarm_id: number;
  recommended_action: Action;
  root_cause_category: string | null;
  confidence: number;
  hypothesis: string;
  evidence: Evidence[];
  status: DispositionStatus;
  engineer_name: string | null;
  engineer_note: string | null;
  final_action: Action | null;
  decided_at: string | null;
  created_at: string;
}

export interface AgentStep {
  seq: number;
  node: string;
  tool_name: string | null;
  tool_args: Record<string, unknown> | null;
  tool_result: Record<string, unknown> | null;
  latency_ms: number | null;
  error: string | null;
  created_at: string;
}

export interface AgentRun {
  id: number;
  alarm_id: number;
  thread_id: string;
  status: RunStatus;
  model: string;
  started_at: string;
  ended_at: string | null;
  error: string | null;
  disposition: Disposition | null;
}

export interface TriageStarted {
  agent_run_id: number;
  thread_id: string;
  alarm_id: number;
}

export interface ReviewRequest {
  decision: ReviewDecision;
  engineer: string;
  final_action?: Action | null;
  note?: string;
}

export const ACTION_LABEL: Record<Action, string> = {
  hold_lot: 'Hold lot',
  continue: 'Continue',
  escalate: 'Escalate',
};
