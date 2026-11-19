import { computed, reactive } from 'vue'
import { workspaceApi } from '../api/client'
import type {
  AgentBubble,
  AgentResult,
  ConversationMessage,
  DirectionKey,
  ModelSelection,
  QuickModelOption,
  TaskStage,
  UploadFileState,
} from '../types'
import { friendlyError, friendlyFileError, friendlyFileSizeError, friendlyStage } from '../utils/friendly'
import { normalizeAgentResult } from '../utils/review'
import { DIRECTION_LABELS, directionPrompt, recommendDirection } from '../utils/direction'

const MAX_FILES = 10
const MAX_FILE_SIZE = 10 * 1024 * 1024

const DEFAULT_MODEL: ModelSelection = {
  providerLabel: '深度求索',
  provider: 'deepseek',
  credentialMode: '本机配置',
  credentialId: null,
  model: null,
  temporaryKey: null,
}

function uid(): string {
  return `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`
}

const state = reactive({
  messages: [] as ConversationMessage[],
  files: [] as UploadFileState[],
  direction: 'free' as DirectionKey,
  customDirection: '',
  recommendReason: '',
  input: '',
  model: { ...DEFAULT_MODEL } as ModelSelection,
  quickModels: [] as QuickModelOption[],
  bubbles: [] as AgentBubble[],
  result: null as AgentResult | null,
  stage: '等待中' as TaskStage,
  confirmPrompt: '',
  taskId: '' as string,
  busy: false,
  notice: '',
  noticeKind: 'info' as 'info' | 'error' | 'success',
})

let activeStreamTask = ''
let confirmedTask = ''

const PLAYBACK_STEP_MS = 600
let playbackQueue: import('../api/client').WorkspaceEvent[] = []
let playbackTimer: ReturnType<typeof setTimeout> | null = null

function resetPlayback(): void {
  playbackQueue = []
  if (playbackTimer !== null) {
    clearTimeout(playbackTimer)
    playbackTimer = null
  }
}

function pumpPlayback(): void {
  if (playbackTimer !== null) return
  const step = (): void => {
    const next = playbackQueue.shift()
    if (!next) {
      playbackTimer = null
      return
    }
    applyEvent(next)
    playbackTimer = setTimeout(step, PLAYBACK_STEP_MS)
  }
  step()
}

function pushMessage(role: ConversationMessage['role'], text: string, extra: Partial<ConversationMessage> = {}): void {
  state.messages.push({
    id: uid(),
    role,
    text,
    createdAt: new Date().toISOString(),
    ...extra,
  })
}

function notify(message: string, kind: 'info' | 'error' | 'success' = 'info'): void {
  state.notice = message
  state.noticeKind = kind
}

function resetModelTempKeyAfterTask(): void {
  if (state.model.credentialMode === '临时使用') {
    state.model.temporaryKey = null
  }
}

export const workspace = {
  state,

  hasStarted: computed(() => state.messages.length > 0),

  async loadQuickModels(): Promise<void> {
    try {
      const data = await workspaceApi.quickModels()
      state.quickModels = data.options || []
    } catch (err) {
      notify(friendlyError(err), 'error')
    }
  },

  setModel(patch: Partial<ModelSelection>): void {
    Object.assign(state.model, patch)
  },

  setDirection(key: DirectionKey): void {
    state.direction = key
    state.recommendReason = ''
  },

  chooseDirection(key: DirectionKey): void {
    if (state.direction === key && !state.customDirection) return
    state.direction = key
    state.customDirection = ''
    state.recommendReason = ''
    pushMessage('助手', directionPrompt(key), {
      kind: 'direction',
      directionKey: key,
      directionLabel: DIRECTION_LABELS[key],
    })
  },

  setCustomDirection(text: string): void {
    state.customDirection = text
    if (text.trim()) state.direction = 'free'
  },

  async addFiles(fileList: File[]): Promise<void> {
    const added: UploadFileState[] = []
    const pending: Array<{ file: File; item: UploadFileState }> = []
    for (const file of fileList) {
      if (state.files.length + added.length >= MAX_FILES) {
        notify('一次最多带上几份文件就够了，先处理这些吧', 'error')
        break
      }
      const allowed = /\.(md|markdown|txt|zip)$/i.test(file.name)
      const item: UploadFileState = {
        uid: uid(),
        name: file.name,
        size: file.size,
        stage: allowed ? '等待中' : '需要检查',
        message: allowed ? '已选好，等待读取' : friendlyFileError(),
        error: allowed ? undefined : 'unsupported',
      }
      state.files.push(item)
      const tracked = state.files[state.files.length - 1]
      added.push(tracked)
      if (!allowed) continue

      if (file.size > MAX_FILE_SIZE) {
        tracked.stage = '需要检查'
        tracked.message = friendlyFileSizeError()
        tracked.error = 'too-large'
        continue
      }
      pending.push({ file, item: tracked })
    }

    if (added.length) {
      pushMessage('用户', '', { kind: 'file', fileUids: added.map((item) => item.uid) })
    }

    for (const { file, item } of pending) {
      item.stage = '读取中'
      item.message = '正在读取内容…'
      const content = await readFile(file, item)
      if (content !== null) {
        item.content = content
        item.stage = '已完成'
        item.message = '已经读好了'
      }
    }
    recommend()
  },

  removeFile(fileUid: string): void {
    const index = state.files.findIndex((file) => file.uid === fileUid)
    if (index >= 0) state.files.splice(index, 1)
    for (const message of state.messages) {
      if (message.fileUids) message.fileUids = message.fileUids.filter((item) => item !== fileUid)
    }
    state.messages = state.messages.filter((message) => message.kind !== 'file' || (message.fileUids?.length ?? 0) > 0)
    recommend()
  },

  clearFiles(): void {
    state.files.splice(0)
    state.recommendReason = ''
  },

  async send(): Promise<void> {
    const text = state.input.trim()
    if (!text && state.files.length === 0) {
      notify('先说点什么，或带一份对话文件过来', 'error')
      return
    }
    if (state.busy) return
    if (state.files.some((file) => file.error)) {
      notify('有一份文件还没准备好，移除它或换一个试试', 'error')
      return
    }

    state.busy = true
    state.notice = ''
    state.bubbles.splice(0)
    state.result = null
    state.confirmPrompt = ''
    resetPlayback()
    pushMessage('用户', text || '帮我看看这些对话')
    pushMessage('助手', '收到，我来帮你看看')
    state.input = ''

    try {
      const response = await workspaceApi.createTask({
        message: text,
        direction: state.direction,
        customDirection: state.customDirection,
        files: state.files.map((file) => ({
          name: file.name,
          size: file.size,
          content: file.content || '',
        })),
        model: { ...state.model },
      })
      activeStreamTask = response.task_id
      confirmedTask = ''
      state.taskId = response.task_id
      state.stage = friendlyStage(response.stage)
      state.recommendReason = response.recommend_reason || state.recommendReason
      workspaceApi.events(response.task_id, handleEvent).catch(() => undefined)
    } catch (err) {
      state.stage = '遇到问题'
      notify(friendlyError(err), 'error')
      pushMessage('助手', friendlyError(err))
    } finally {
      state.busy = false
      resetModelTempKeyAfterTask()
    }
  },

  async confirm(confirmed: boolean): Promise<void> {
    if (!state.taskId || state.busy) return
    state.busy = true
    resetPlayback()
    state.confirmPrompt = ''
    try {
      const response = await workspaceApi.confirm(state.taskId, {
        confirmed,
        note: state.customDirection || undefined,
        model: { ...state.model },
      })
      confirmedTask = state.taskId
      state.stage = friendlyStage(response.stage)
      state.confirmPrompt = ''
      if (confirmed && response.result) showResult(response.result)
      pushMessage('助手', confirmed ? '好的，已经帮你保存好了' : '好的，这次就先不采纳')
    } catch (err) {
      state.stage = '遇到问题'
      notify(friendlyError(err), 'error')
    } finally {
      state.busy = false
      resetModelTempKeyAfterTask()
    }
  },

  reset(): void {
    state.messages.splice(0)
    state.bubbles.splice(0)
    state.files.splice(0)
    state.result = null
    state.confirmPrompt = ''
    state.stage = '等待中'
    state.taskId = ''
  },
}

function recommend(): void {
  const withContent = state.files.filter((file) => file.content)
  if (withContent.length === 0) return
  const rec = recommendDirection(state.files, state.input)
  state.direction = rec.key
  state.recommendReason = rec.reason
}

async function readFile(file: File, item: UploadFileState): Promise<string | null> {
  try {
    if (/\.zip$/i.test(file.name)) {
      return await blobToBase64(file)
    }
    return await file.text()
  } catch {
    item.stage = '需要检查'
    item.message = friendlyFileError()
    item.error = 'unreadable'
    notify(friendlyFileError(), 'error')
    return null
  }
}

function blobToBase64(blob: Blob): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader()
    reader.onload = () => resolve(String(reader.result).split(',')[1] || '')
    reader.onerror = () => reject(new Error('unreadable'))
    reader.readAsDataURL(blob)
  })
}

function showResult(raw: AgentResult | null | undefined): void {
  const result = normalizeAgentResult(raw)
  if (!result) return
  state.result = result
  const existing = [...state.messages]
    .reverse()
    .find((item) => item.kind === 'result')
  if (
    existing &&
    existing.result?.title === result.title &&
    existing.result?.report_id === result.report_id
  ) {
    existing.result = result
    existing.text = result.summary
    return
  }
  pushMessage('助手', result.summary, { kind: 'result', result })
}

function applyEvent(event: import('../api/client').WorkspaceEvent): void {
  if (confirmedTask && state.taskId === confirmedTask) return
  if (event.stage) state.stage = friendlyStage(event.stage)
  if (event.bubble) {
    const existing = state.bubbles.find((item) => item.id === event.bubble!.id)
    if (existing) Object.assign(existing, event.bubble)
    else state.bubbles.push({ ...event.bubble! })

    const message = state.messages.find((item) => item.bubbleId === event.bubble!.id)
    if (message) {
      message.text = event.bubble.message
      message.agentState = event.bubble.state
    } else {
      pushMessage(event.bubble.role, event.bubble.message, {
        kind: 'agent',
        bubbleId: event.bubble.id,
        agentState: event.bubble.state,
      })
    }
  }
  if (event.result) showResult(event.result)
  if (event.confirmPrompt) state.confirmPrompt = event.confirmPrompt
  if (activeStreamTask && state.stage === '已完成') activeStreamTask = ''
}

function handleEvent(event: import('../api/client').WorkspaceEvent): void {
  if (confirmedTask && state.taskId === confirmedTask) return
  playbackQueue.push(event)
  pumpPlayback()
}
