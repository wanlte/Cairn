import type { ApiErrorBody } from '../types'

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
    throw new ApiError(response.status, payload as ApiErrorBody | null)
  }
  return payload as T
}

export const api = {
  get: <T>(path: string) => request<T>('GET', path),
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
