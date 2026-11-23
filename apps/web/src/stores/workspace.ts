import { computed, reactive } from 'vue'
import {
  metricsApi,
  workspaceApi,
  type WorkspaceHistory,
  type WorkspaceTaskResponse,
} from '../api/client'
import type {
  AgentBubble,
  AgentResult,
  ConversationMessage,
  DirectionKey,
  ModelSelection,
  PromptPreset,
  QuickModelOption,
  TaskStage,
  UploadFileState,
} from '../types'
import { friendlyError, friendlyFileError, friendlyFileSizeError, friendlyStage } from '../utils/friendly'
import { normalizeAgentResult } from '../utils/review'
import { BUILTIN_PROMPTS, DIRECTION_LABELS, recommendDirection } from '../utils/direction'

const MAX_FILES = 10
const MAX_FILE_SIZE = 10 * 1024 * 1024
const PROMPT_STORAGE_KEY = 'cairn_saved_prompts'
const MAX_SELECTED_PROMPTS = 3

function readSavedPrompts(): PromptPreset[] {
  try {
    const raw = JSON.parse(localStorage.getItem(PROMPT_STORAGE_KEY) || '[]')
    if (!Array.isArray(raw)) return []
    return raw.filter(
      (item): item is PromptPreset =>
        Boolean(item) &&
        typeof item.id === 'string' &&
        typeof item.label === 'string' &&
        typeof item.text === 'string' &&
        typeof item.direction === 'string',
    )
  } catch {
    return []
  }
}

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
  savedPrompts: readSavedPrompts(),
  selectedPromptIds: [] as string[],
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
  history: [] as WorkspaceTaskResponse[],
  historyLoading: false,
})

const availablePrompts = computed(() => [...BUILTIN_PROMPTS, ...state.savedPrompts])
const selectedPrompts = computed(() =>
  state.selectedPromptIds
    .map((id) => availablePrompts.value.find((item) => item.id === id))
    .filter((item): item is PromptPreset => Boolean(item)),
)

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
  selectedPrompts,
  availablePrompts,

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

  togglePrompt(id: string): void {
    const index = state.selectedPromptIds.indexOf(id)
    if (index >= 0) {
      state.selectedPromptIds.splice(index, 1)
      return
    }
    if (state.selectedPromptIds.length >= MAX_SELECTED_PROMPTS) {
      notify('一次带上三条提示词就够了，先取消一条再选', 'error')
      return
    }
    const prompt = availablePrompts.value.find((item) => item.id === id)
    if (!prompt) return
    state.selectedPromptIds.push(id)
    if (!state.customDirection) state.direction = prompt.direction
  },

  addPrompt(label: string, text: string, direction: DirectionKey): void {
    const cleanLabel = label.trim()
    const cleanText = text.trim()
    if (!cleanLabel || !cleanText) {
      notify('给提示词起个名字，再写清楚想让我做什么', 'error')
      return
    }
    const preset: PromptPreset = {
      id: `custom-${Date.now().toString(36)}`,
      label: cleanLabel,
      text: cleanText,
      direction,
      custom: true,
    }
    state.savedPrompts.push(preset)
    localStorage.setItem(PROMPT_STORAGE_KEY, JSON.stringify(state.savedPrompts))
    state.selectedPromptIds.push(preset.id)
    notify('这条提示词已经长期保存', 'success')
  },

  removePrompt(id: string): void {
    state.savedPrompts = state.savedPrompts.filter((item) => item.id !== id)
    state.selectedPromptIds = state.selectedPromptIds.filter((item) => item !== id)
    localStorage.setItem(PROMPT_STORAGE_KEY, JSON.stringify(state.savedPrompts))
  },

  clearSelectedPrompts(): void {
    state.selectedPromptIds.splice(0)
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
    pushMessage('助手', workingText(), { kind: 'working' })
    state.input = ''

    try {
      const response = await workspaceApi.createTask({
        message: text,
        direction: state.direction,
        customDirection: [
          ...selectedPrompts.value.map((item) => item.text),
          state.customDirection,
        ]
          .map((item) => item.trim())
          .filter(Boolean)
          .join('\n'),
        files: state.files.map((file) => ({
          name: file.name,
          size: file.size,
          content: file.content || '',
        })),
        model: { ...state.model },
      })
      void metricsApi.track('task_started', { direction: state.direction })
      activeStreamTask = response.task_id
      confirmedTask = ''
      state.taskId = response.task_id
      state.stage = friendlyStage(response.stage)
      state.recommendReason = response.recommend_reason || state.recommendReason
      workspaceApi.events(response.task_id, handleEvent).catch(() => {
        state.messages = state.messages.filter((item) => item.kind !== 'working')
      })
      void workspaceApi.list().then((items) => { state.history = items }).catch(() => undefined)
    } catch (err) {
      state.messages = state.messages.filter((item) => item.kind !== 'working')
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

  async loadHistory(limit = 50): Promise<void> {
    state.historyLoading = true
    try {
      state.history = await workspaceApi.list(limit)
    } catch (err) {
      notify(friendlyError(err), 'error')
    } finally {
      state.historyLoading = false
    }
  },

  async openTask(taskId: string): Promise<void> {
    if (state.busy || !taskId) return
    resetPlayback()
    activeStreamTask = ''
    confirmedTask = ''
    state.busy = true
    try {
      const data: WorkspaceHistory = await workspaceApi.history(taskId)
      state.messages.splice(0)
      state.bubbles.splice(0)
      state.files.splice(0)
      for (const item of data.messages) {
        if (item.kind === 'result' && item.result) {
          const result = normalizeAgentResult(item.result)
          if (result) {
            state.messages.push({
              id: item.id,
              role: '助手',
              text: result.summary,
              kind: 'result',
              result,
              createdAt: item.created_at || new Date().toISOString(),
            })
          }
        } else if (item.kind === 'agent') {
          const agentState =
            item.agent_state === '进行中' || item.agent_state === '需要确认'
              ? item.agent_state
              : '完成'
          state.messages.push({
            id: item.id,
            role: item.role as ConversationMessage['role'],
            text: item.text,
            kind: 'agent',
            bubbleId: item.bubble_id || undefined,
            agentState,
            createdAt: item.created_at || new Date().toISOString(),
          })
          if (item.bubble_id) {
            state.bubbles.push({
              id: item.bubble_id,
              role: item.role as AgentBubble['role'],
              message: item.text,
              state: agentState,
            })
          }
        } else {
          state.messages.push({
            id: item.id,
            role: item.role === '用户' ? '用户' : '助手',
            text: item.text,
            kind: 'text',
            createdAt: item.created_at || new Date().toISOString(),
          })
        }
      }
      state.taskId = data.task.task_id
      state.result = normalizeAgentResult(data.task.result) || null
      state.stage = friendlyStage(data.task.stage)
      state.confirmPrompt = data.task.confirm_prompt || ''
      state.direction = (data.task.direction as DirectionKey) || 'free'
      state.notice = '已载入这次对话，可以直接继续问'
      state.noticeKind = 'success'
    } catch (err) {
      notify(friendlyError(err), 'error')
    } finally {
      state.busy = false
    }
  },
}

function workingText(): string {
  const label = DIRECTION_LABELS[state.direction]
  if (state.files.length === 0) return '正在想怎么回答你…'
  if (state.direction === 'growth') return '正在根据你提供的对话更新成长画像…'
  if (state.direction === 'free') return '正在理解你的问题，并去对话里找依据…'
  return `正在按「${label}」梳理对话，几位小伙伴要忙一会儿…`
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
  // 只有带报告编号的结果（复盘/画像修订）才更新同一张卡片；
  // 每轮问答都是独立回答，应当新增卡片，不能被上一轮的同名标题吞掉。
  if (
    result.report_id != null &&
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
  if (state.messages.some((item) => item.kind === 'working')) {
    state.messages = state.messages.filter((item) => item.kind !== 'working')
  }
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
