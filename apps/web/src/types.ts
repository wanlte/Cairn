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
