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
  feedback: Record<string, unknown> | null
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
  period: string
  status: string
  overview: Record<string, unknown>
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
  kind?: 'text' | 'result' | 'file' | 'agent'
  fileUids?: string[]
  bubbleId?: string
  agentState?: '进行中' | '完成' | '需要确认'
  result?: AgentResult
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
  nextLabel?: string
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
