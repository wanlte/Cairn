import type {
  AgentBubble,
  AgentResult,
  ApiErrorBody,
  ConversationSummary,
  Coverage,
  CounterfactualEntry,
  DailyQuestion,
  DecisionResult,
  DirectionKey,
  ExportResult,
  PairAnalysisResult,
  IngestionPreview,
  MetricsOverview,
  ModelSelection,
  PlanResponse,
  QuickModelOption,
  ReviewItem,
  ReviewReport,
  ActionItemRecord,
  AppealRecord,
  DesirabilityFlag,
  DriftCurve,
  EvidenceChain,
  RelationGraph,
  SimulationResult,
  TaskStage,
  TimelineResponse,
  WeeklyFill,
} from '../types'

const BASE = '/api/v1'

export class ApiError extends Error {
  status: number
  body: ApiErrorBody | null

  constructor(status: number, body: ApiErrorBody | null) {
    super(body?.message || `请求失败（${status}）`)
    this.status = status
    this.body = body
  }
}

function authHeaders(): Record<string, string> {
  const token = localStorage.getItem('cairn_token')
  return token ? { Authorization: `Bearer ${token}` } : {}
}

function handleUnauthorized(status: number): void {
  if (status !== 401) return
  localStorage.removeItem('cairn_token')
  localStorage.removeItem('cairn_email')
  if (typeof window !== 'undefined' && window.location.pathname !== '/login') {
    window.location.assign('/login')
  }
}

async function parseBody(response: Response): Promise<any> {
  const text = await response.text()
  if (!text) return null
  try {
    return JSON.parse(text)
  } catch {
    return text
  }
}

async function request<T>(
  method: string,
  path: string,
  body?: unknown,
  extraHeaders: Record<string, string> = {},
): Promise<T> {
  const response = await fetch(`${BASE}${path}`, {
    method,
    headers: {
      'Content-Type': 'application/json',
      ...authHeaders(),
      ...extraHeaders,
    },
    body: body === undefined ? undefined : JSON.stringify(body),
  })
  const payload = await parseBody(response)
  if (!response.ok) {
    handleUnauthorized(response.status)
    throw new ApiError(response.status, payload as ApiErrorBody | null)
  }
  return payload as T
}

export const api = {
  get: <T>(path: string) => request<T>('GET', path),
  getText: async (path: string): Promise<string> => {
    const response = await fetch(`${BASE}${path}`, {
      headers: { ...authHeaders() },
    })
    if (!response.ok) {
      const payload = await parseBody(response)
      handleUnauthorized(response.status)
      throw new ApiError(response.status, payload as ApiErrorBody | null)
    }
    return response.text()
  },
  post: <T>(path: string, body?: unknown, headers?: Record<string, string>) =>
    request<T>('POST', path, body, headers),
  put: <T>(path: string, body?: unknown) => request<T>('PUT', path, body),
  patch: <T>(path: string, body?: unknown) => request<T>('PATCH', path, body),
  delete: <T>(path: string, headers?: Record<string, string>) =>
    request<T>('DELETE', path, undefined, headers),

  async stream(path: string, onEvent: (data: any) => void): Promise<void> {
    const response = await fetch(`${BASE}${path}`, {
      method: 'GET',
      headers: {
        Accept: 'text/event-stream',
        ...authHeaders(),
      },
    })
    if (!response.ok) {
      const payload = await parseBody(response)
      handleUnauthorized(response.status)
      throw new ApiError(response.status, payload as ApiErrorBody | null)
    }
    if (!response.body) throw new Error('浏览器不支持流式响应')

    const reader = response.body.getReader()
    const decoder = new TextDecoder()
    let buffer = ''
    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      buffer += decoder.decode(value, { stream: true })
      const frames = buffer.split('\n\n')
      buffer = frames.pop() || ''
      for (const frame of frames) {
        const line = frame.split('\n').find((item) => item.startsWith('data: '))
        if (!line) continue
        try {
          onEvent(JSON.parse(line.slice(6)))
        } catch {
          // 忽略坏帧
        }
      }
    }
  },
}

export interface WorkspaceFilePayload {
  name: string
  size: number
  content: string
}

export interface WorkspaceTaskPayload {
  message: string
  direction: DirectionKey
  customDirection?: string
  files: WorkspaceFilePayload[]
  model: ModelSelection
}

function toBackendModel(model: ModelSelection) {
  return {
    provider: model.provider,
    model: model.model,
    credential_mode: model.credentialMode,
    credential_id: model.credentialId,
    temporary_api_key: model.temporaryKey,
  }
}

export interface WorkspaceEvent {
  stage: TaskStage
  bubble?: AgentBubble
  message?: string
  result?: AgentResult
  confirmPrompt?: string
}

export interface WorkspaceTaskResponse {
  task_id: string
  stage: string
  recommend_reason?: string | null
  confirm_prompt?: string | null
  result?: AgentResult | null
  report_id?: number | null
  user_message?: string | null
  intent?: string
  direction?: string | null
  pinned?: boolean
  archived?: boolean
  created_at?: string | null
}

export interface HistoryMessage {
  id: string
  role: string
  text: string
  kind: string
  bubble_id?: string | null
  agent_state?: string | null
  result?: AgentResult | null
  created_at?: string | null
}

export interface WorkspaceHistory {
  task: WorkspaceTaskResponse
  messages: HistoryMessage[]
}

export interface WorkspaceConfirmBody {
  confirmed: boolean
  note?: string
  model: ModelSelection
}

export const workspaceApi = {
  quickModels: () => api.get<{ options: QuickModelOption[] }>('/credentials/quick-options'),

  createTask: (payload: WorkspaceTaskPayload) =>
    api.post<WorkspaceTaskResponse>('/workspace/tasks', {
      message: payload.message,
      direction: payload.direction,
      custom_direction: payload.customDirection,
      files: payload.files,
      model: toBackendModel(payload.model),
    }),

  task: (taskId: string) => api.get<WorkspaceTaskResponse>(`/workspace/tasks/${taskId}`),

  list: (limit = 50, archived?: boolean) =>
    api.get<WorkspaceTaskResponse[]>(
      `/workspace/tasks?limit=${limit}${archived === undefined ? '' : `&archived=${archived}`}`,
    ),

  patch: (taskId: string, patch: { pinned?: boolean; archived?: boolean }) =>
    api.patch<WorkspaceTaskResponse>(`/workspace/tasks/${taskId}`, patch),

  tidy: (taskKeys: string[], archived: boolean) =>
    api.post<{ updated: number }>('/workspace/tasks/tidy', {
      task_keys: taskKeys,
      archived,
    }),

  history: (taskId: string) =>
    api.get<WorkspaceHistory>(`/workspace/tasks/${taskId}/history`),

  events: (taskId: string, onEvent: (data: WorkspaceEvent) => void) =>
    api.stream(`/workspace/tasks/${taskId}/events`, onEvent),

  confirm: (taskId: string, body: WorkspaceConfirmBody) =>
    api.post<WorkspaceTaskResponse>(`/workspace/tasks/${taskId}/confirm`, {
      confirmed: body.confirmed,
      note: body.note,
      model: toBackendModel(body.model),
    }),
}

export const reviewApi = {
  list: () => api.get<ReviewReport[]>('/reviews'),

  get: (reportId: number) => api.get<ReviewReport>(`/reviews/${reportId}`),

  exportText: (reportId: number) => api.getText(`/reviews/${reportId}/export`),

  verifyAction: (actionId: number, note?: string) =>
    api.post<ActionItemRecord>(`/reviews/action-items/${actionId}/verify`, { note: note || null }),

  reopenAction: (actionId: number, note?: string) =>
    api.post<ActionItemRecord>(`/reviews/action-items/${actionId}/reopen`, { note: note || null }),

  feedback: (itemId: number, decision: 'AGREE' | 'DISAGREE') =>
    api.post<ReviewItem>(`/reviews/items/${itemId}/feedback`, { decision }),
}

export interface IngestPreviewPayload {
  source_type: string
  text?: string
  base64?: string
  filename?: string
}

export interface IngestCommitResult {
  conversation_id: number
  turn_count: number
  duplicate: boolean
}

export const ingestionApi = {
  preview: (payload: IngestPreviewPayload) =>
    api.post<IngestionPreview>('/ingestion/preview', payload),

  commit: (previewId: string) =>
    api.post<IngestCommitResult>('/ingestion/commit', {
      preview_id: previewId,
      corrections: [],
    }),

  conversations: () => api.get<{ items: ConversationSummary[] }>('/ingestion/conversations'),
}

export interface CounterfactualPayload {
  prompt_type: string
  content: string
  source_label?: string
}

export const samplesApi = {
  coverage: () => api.get<Coverage>('/samples/coverage'),

  listCounterfactuals: () => api.get<CounterfactualEntry[]>('/samples/counterfactuals'),

  addCounterfactual: (payload: CounterfactualPayload) =>
    api.post<CounterfactualEntry>('/samples/counterfactuals', payload),

  deleteCounterfactual: (entryId: number) =>
    api.delete(`/samples/counterfactuals/${entryId}`),
}

export const timelineApi = {
  events: (eventTypes?: string[], limit = 200) => {
    const query = new URLSearchParams()
    eventTypes?.forEach((type) => query.append('event_types', type))
    query.set('limit', String(limit))
    return api.get<TimelineResponse>(`/timeline/events?${query.toString()}`)
  },
}

export const analysisApi = {
  desirability: () => api.get<DesirabilityFlag[]>('/analysis/desirability'),

  evidenceChain: (itemId: number) =>
    api.get<EvidenceChain>(`/analysis/evidence-chain/${itemId}`),

  submitAppeal: (itemId: number, reason: string) =>
    api.post<AppealRecord>(`/analysis/appeals?item_id=${itemId}`, { reason }),

  listAppeals: () => api.get<AppealRecord[]>('/analysis/appeals'),

  resolveAppeal: (appealId: number, decision: 'ACCEPTED' | 'REJECTED', note?: string) =>
    api.post<AppealRecord>(`/analysis/appeals/${appealId}/resolve`, { decision, note }),
}

export const insightsApi = {
  drift: (group?: string) =>
    api.get<DriftCurve>(`/insights/drift${group ? `?group=${encodeURIComponent(group)}` : ''}`),

  graph: () => api.get<RelationGraph>('/insights/graph'),

  rebuildGraph: () => api.post<{ edges: number }>('/insights/graph/rebuild'),
}

export interface PlanGeneratePayload {
  goal: string
  provider?: string | null
  model?: string | null
  credential_id?: number | null
  temporary_api_key?: string | null
}

export interface WeeklyFillPayload {
  week: string
  done: string
  blocked: string
  learning: string
}

export const planningApi = {
  current: () => api.get<PlanResponse>('/plans/current'),

  list: () => api.get<PlanResponse[]>('/plans'),

  generate: (payload: PlanGeneratePayload) =>
    api.post<PlanResponse>('/plans/generate', payload),

  fillWeekly: (blueprintId: number, payload: WeeklyFillPayload) =>
    api.post<WeeklyFill>(`/plans/${blueprintId}/weekly`, payload),
}

export interface ExtensionPayload {
  scenario?: string
  choice?: string
  question?: string
  pair_id?: number
  provider?: string | null
  model?: string | null
  credential_id?: number | null
  temporary_api_key?: string | null
}

export const extensionsApi = {
  simulate: (payload: ExtensionPayload) =>
    api.post<SimulationResult>('/extensions/simulate', payload),

  decide: (payload: ExtensionPayload) =>
    api.post<DecisionResult>('/extensions/decide', payload),

  daily: () => api.get<DailyQuestion>('/extensions/daily'),

  answerDaily: (questionId: number, answer: string) =>
    api.post<DailyQuestion>(`/extensions/daily/${questionId}/answer`, { answer }),

  pairAnalysis: (payload: ExtensionPayload) =>
    api.post<PairAnalysisResult>('/extensions/pair-analysis', payload),
}

export const exportsApi = {
  get: (kind: string, format: 'json' | 'md' | 'html') =>
    api.get<ExportResult>(`/exports/${kind}?format=${format}`),
}

export const metricsApi = {
  overview: (windowDays: number) =>
    api.get<MetricsOverview>(`/metrics/overview?window_days=${windowDays}`),

  track: (eventType: string, payload: Record<string, unknown> = {}) =>
    api.post('/metrics/events', { event_type: eventType, payload }).catch(() => undefined),
}
