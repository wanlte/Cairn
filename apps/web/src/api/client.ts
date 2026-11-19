import type {
  AgentBubble,
  AgentResult,
  ApiErrorBody,
  DirectionKey,
  ModelSelection,
  QuickModelOption,
  ReviewItem,
  ReviewReport,
  ActionItemRecord,
  TaskStage,
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
}

export interface WorkspaceConfirmBody {
  confirmed: boolean
  note?: string
  model: ModelSelection
}

export const workspaceApi = {
  quickModels: () => api.get<{ options: QuickModelOption[] }>('/credentials/quick-options'),

  createTask: (payload: WorkspaceTaskPayload) =>
    api.post<WorkspaceTaskResponse>('/workspace/tasks', payload),

  task: (taskId: string) => api.get<WorkspaceTaskResponse>(`/workspace/tasks/${taskId}`),

  events: (taskId: string, onEvent: (data: WorkspaceEvent) => void) =>
    api.stream(`/workspace/tasks/${taskId}/events`, onEvent),

  confirm: (taskId: string, body: WorkspaceConfirmBody) =>
    api.post<WorkspaceTaskResponse>(`/workspace/tasks/${taskId}/confirm`, body),
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
