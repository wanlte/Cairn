export interface TokenResponse {
  access_token: string
  refresh_token: string
  token_type: string
}

export interface ApiErrorBody {
  code: string
  message: string
  request_id?: string
  retryable?: boolean
}

export interface IngestionPreviewTurn {
  turn_id: string
  seq: number
  user_content: string
  assistant_content: string
  asked_at: string | null
  time_precision: string
  role_confidence: number
  low_confidence: boolean
}

export interface IngestionPreview {
  preview_id: string
  title: string
  source_type: string
  source_ref: string
  total_turns: number
  low_confidence_count: number
  anomalies: string[]
  turns: IngestionPreviewTurn[]
}

export interface ConversationSummary {
  id: number
  title: string
  source_type: string
  source_ref: string
  content_hash: string
  created_at: string
}

export interface ExtractionRun {
  id: number
  conversation_id: number
  status: string
  total: number
  processed: number
  failed: number
  prompt_version: string
  model: string | null
  provider: string | null
  error_json: Array<Record<string, string>>
  created_at: string
  finished_at: string | null
}

export interface Fragment {
  id: number
  kind: string
  turn_pair_id: number
  payload: Record<string, unknown>
  content_hash: string
  created_at: string
}

export interface ReviewItem {
  id: number
  section: string
  verdict: string | null
  attribution: string | null
  fragment_id: number | null
  evidence_fragment_ids: number[]
  payload: Record<string, unknown>
  feedback: { decision?: string; note?: string | null } | null
  confidence_low?: number | null
  confidence_high?: number | null
  reasoning_chain?: string[]
  conflicts_with?: number[]
  appeal_status?: string
}

export interface AppealRecord {
  id: number
  item_id: number
  reason: string
  status: string
  resolution_note: string | null
  created_at: string
  resolved_at: string | null
}

export interface DesirabilityFlag {
  fragment_id: number
  score: number
  signals: string[]
  summary: string
}

export interface EvidenceChain {
  item_id: number
  section: string
  conclusion: string
  reasoning_chain: string[]
  confidence_low: number | null
  confidence_high: number | null
  conflicts_with: number[]
  appeal_status: string
  evidence: { fragment_id: number; kind: string | null; payload: Record<string, unknown> }[]
}

export interface ReviewDistributionEntry {
  domain?: string
  topic?: string
  count: number
}

export interface ReviewOverview {
  dialogue_count?: number
  domain_distribution?: ReviewDistributionEntry[]
  investment_distribution?: ReviewDistributionEntry[]
  comparison_with_last_period?: string
}

export interface ActionItemRecord {
  id: number
  report_id: number
  period: string | null
  content: string
  verification: string
  status: 'PENDING' | 'VERIFIED' | 'REOPENED'
  verification_note: string | null
  evidence_fragment_ids: number[]
  verified_at: string | null
}

export interface ReviewReport {
  id: number
  user_id: number
  period: string
  status: string
  overview: ReviewOverview
  prompt_version: string
  model: string | null
  provider: string | null
  error_code: string | null
  created_at: string
  items: ReviewItem[]
  action_items: ActionItemRecord[]
}

export interface ProfileClaim {
  id: number
  group: string
  key: string
  value: string
  evidence_fragment_ids: number[]
  source: string
  user_corrected: boolean
  is_deleted: boolean
  created_at: string
}

export interface ProfileSnapshot {
  id: number
  period: string
  status: string
  previous_snapshot_id: number | null
  prompt_version: string
  model: string | null
  provider: string | null
  error_code: string | null
  created_at: string
  claims: ProfileClaim[]
}

export interface RetrievalSearchResponse {
  query: string
  items: RetrievalItem[]
  used_vector: boolean
  used_bm25: boolean
  reranked: boolean
}

export interface RetrievalAskResponse {
  answer: string
  sources: RetrievalItem[]
  profile_used: boolean
}

export interface RetrievalItem {
  fragment_id: number
  kind: string
  score: number
  bm25_score: number
  vector_score: number
  rerank_score: number | null
  payload: Record<string, unknown>
  domain: string | null
  platform: string | null
  created_at: string | null
}

export interface ProfileDiff {
  from_period: string
  to_period: string
  added: ProfileClaim[]
  removed: ProfileClaim[]
  changed: Array<Record<string, unknown>>
}

export interface Credential {
  id: number
  name: string
  provider: string
  base_url: string | null
  model: string | null
  api_key_masked: string
  is_active: boolean
  capabilities: Record<string, unknown> | null
  created_at: string
}

export interface UsageRow {
  bucket: string
  task_type: string
  provider: string
  model: string
  calls: number
  prompt_tokens: number
  completion_tokens: number
  cost_cny: number
}

export type ProviderLabel = '深度求索' | '火山引擎' | '腾讯混元' | '兼容接口'
export type CredentialMode = '本机配置' | '已保存凭证' | '临时使用'
export type AgentRoleLabel = '整理师' | '复盘师' | '画像师' | '问答教练' | '审核员'
export type DirectionKey = 'weekly' | 'project' | 'conversation' | 'growth' | 'free'

export interface ModelSelection {
  providerLabel: ProviderLabel
  provider: string
  credentialMode: CredentialMode
  credentialId: number | null
  model: string | null
  temporaryKey: string | null
}

export interface UploadFileState {
  uid: string
  name: string
  size: number
  stage: '等待中' | '读取中' | '识别中' | '已完成' | '需要检查'
  message: string
  error?: string
  content?: string
}

export interface ConversationMessage {
  id: string
  role: '用户' | '助手' | AgentRoleLabel
  text: string
  createdAt: string
  kind?: 'text' | 'result' | 'file' | 'agent' | 'working' | 'direction'
  fileUids?: string[]
  bubbleId?: string
  agentState?: '进行中' | '完成' | '需要确认'
  result?: AgentResult
  directionKey?: DirectionKey
  directionLabel?: string
}

export interface AgentBubble {
  id: string
  role: AgentRoleLabel
  message: string
  state: '进行中' | '完成' | '需要确认'
}

export interface AgentResult {
  kind: '复盘' | '画像' | '问答' | '整理'
  title: string
  summary: string
  suggestions: string[]
  next_label?: string | null
  report_id?: number | null
}

export type TaskStage = '等待中' | '处理中' | '请确认' | '已完成' | '遇到问题'

export interface WorkspaceTask {
  taskId: string
  stage: TaskStage
  direction: DirectionKey
  message: string
  recommendReason?: string
}

export interface DirectionOption {
  key: DirectionKey
  label: string
  description: string
  prompt: string
}

export interface PromptPreset {
  id: string
  label: string
  text: string
  direction: DirectionKey
  custom?: boolean
}

export interface QuickSavedCredential {
  id: number
  name: string
  model: string | null
}

export interface QuickModelOption {
  provider: string
  label: ProviderLabel
  model: string | null
  fromEnvironment: boolean
  saved: QuickSavedCredential[]
}

export interface Coverage {
  score: number
  level: string
  low_confidence: boolean
  span_days: number
  scenarios: number
  emotion_density: number
  sources: number
  counterfactuals: number
  reasons: string[]
  summary: string
}

export interface CounterfactualEntry {
  id: number
  prompt_type: string
  content: string
  source_label: string | null
  created_at: string
}

export interface TimelineEvent {
  id: string
  event_type: string
  occurred_at: string | null
  time_precision: string
  title: string
  summary: string
  source_type: string | null
  ref_id: number
  low_confidence: boolean
}

export interface TimelineResponse {
  items: TimelineEvent[]
  total: number
  span_days: number
  low_precision_count: number
}

export interface DriftClaim {
  key: string
  value: string
  group: string
}

export interface DriftPoint {
  snapshot_id: number
  period: string
  created_at: string
  claims: DriftClaim[]
  triggers: Record<string, number>
}

export interface DriftCurve {
  points: DriftPoint[]
  total_snapshots: number
}

export interface GraphNode {
  id: string
  label: string
  kind: string
  weight: number
}

export interface GraphEdge {
  source: string
  target: string
  kind: string
  weight: number
}

export interface RelationGraph {
  nodes: GraphNode[]
  edges: GraphEdge[]
}

export interface WeeklyFill {
  id: number
  blueprint_id: number
  week: string
  done: string
  blocked: string
  learning: string
  created_at: string
}

export interface PlanPayload {
  feasibility?: { assumption: string; evidence: string; risk: string; verdict: string }
  premortem?: { scenario: string; signal: string; countermeasure: string }[]
  two_minute?: string
  if_then?: { condition: string; action: string }[]
  conflicts?: { goal_a: string; goal_b: string; reason: string }[]
  attribution?: { layer: string; explanation: string }[]
}

export interface PlanResponse {
  id: number
  user_id: number
  goal: string
  status: string
  payload: PlanPayload
  coverage: Record<string, unknown>
  prompt_version: string
  model: string | null
  provider: string | null
  created_at: string
  weekly_fills: WeeklyFill[]
}

export interface SimulationResult {
  id: number
  scenario: string
  choice: string
  payload: {
    paths?: { choice: string; outcome: string; signal: string }[]
    advice?: string
  }
  created_at: string
}

export interface DecisionResult {
  suggestion: string
  reasons: string[]
  first_step: string
}

export interface DailyQuestion {
  id: number
  day: string
  question: string
  answer: string
  created_at: string
}

export interface PairAnalysisResult {
  pair_id: number
  summary: string
  mismatches: { situation: string; you: string; them: string; repair: string }[]
}

export interface ExportResult {
  kind: string
  format: string
  filename: string
  content: string
}

export interface MetricPoint {
  bucket: string
  value: number
}

export interface MetricPair {
  label: string
  fast: number
  accurate: number
  sample: number
}

export interface SystemMetrics {
  total_requests: number
  success_rate: number
  error_codes: { code: string; count: number }[]
  latency_p50_ms: number
  latency_p95_ms: number
  task_completion_rate: number
  stage_latency_ms: { stage: string; count: number }[]
  latency_trend: MetricPoint[]
}

export interface QualityMetrics {
  schema_pass_rate: number
  evidence_hit_rate: number
  profile_stability: number
  appeal_rate: number
  appeal_correction_rate: number
  confidence_avg: number
  coverage_avg: number
  coverage_distribution: { level: string; count: number }[]
  speed_accuracy: MetricPair[]
}

export interface CostMetrics {
  total_cost_cny: number
  total_calls: number
  total_tokens: number
  retry_rate: number
  fallback_rate: number
  failure_rate: number
  by_model: { model: string; calls: number; cost: number; tokens: number }[]
  cost_trend: MetricPoint[]
}

export interface BehaviorMetrics {
  funnel: { label: string; count: number }[]
  feature_penetration: { feature: string; count: number; rate: number }[]
  events_by_day: MetricPoint[]
}

export interface ValueMetrics {
  coverage_improvement: number
  weekly_streak: number
  weekly_fills: number
  export_count: number
  open_api_calls: number
  pair_analysis_count: number
}

export interface SecurityMetrics {
  denied_requests: number
  revoked_keys: number
  consent_coverage: number
  audit_events: number
  redaction_hits: number
}

export interface MetricsOverview {
  window_days: number
  generated_at: string
  system: SystemMetrics
  quality: QualityMetrics
  cost: CostMetrics
  behavior: BehaviorMetrics
  value: ValueMetrics
  security: SecurityMetrics
  headline: Record<string, number | string>
}
