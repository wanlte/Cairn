import { ApiError } from '../api/client'
import type { AgentRoleLabel, ProviderLabel, TaskStage } from '../types'

const roleMessages: Record<AgentRoleLabel, Record<string, string>> = {
  整理师: { start: '整理师正在梳理你提供的内容…', done: '内容已经整理好了' },
  复盘师: { start: '复盘师正在认真回顾这段时间…', done: '复盘已经写好' },
  画像师: { start: '画像师正在更新你的成长画像…', done: '画像已经更新' },
  问答教练: { start: '问答教练正在翻找相关记录…', done: '教练已经准备好回答' },
  审核员: { start: '审核员正在核对每一条依据…', done: '核对完成，看起来没问题' },
}

const stageMessages: Record<TaskStage, string> = {
  等待中: '正在排队，马上就轮到你',
  处理中: '正在处理，请稍等片刻',
  请确认: '有几处需要你确认一下',
  已完成: '都处理好了',
  遇到问题: '遇到了一点小状况',
}

const providerLabels: Record<string, ProviderLabel> = {
  deepseek: '深度求索',
  volcengine: '火山引擎',
  hunyuan: '腾讯混元',
  openai_compat: '兼容接口',
}

const friendlyErrors: Array<[RegExp, string]> = [
  [/credential/i, '模型还没配置好，选一个模型就能继续'],
  [/connect|timeout|network|econn/i, '模型暂时无法连接，请检查配置后重试'],
  [/unauthor|401|forbidden|403|key/i, '这个密钥好像不太对，换一个再试试'],
  [/rate.?limit|429|quota/i, '模型有点忙，稍等一会儿再试'],
  [/not.?found|404/i, '没有找到对应的内容，换个方式试试'],
  [/unsupported|capability|schema/i, '当前模型不支持这个能力，换一个模型试试'],
]

export function friendlyRoleStart(role: AgentRoleLabel): string {
  return roleMessages[role]?.start || `${role}正在处理…`
}

export function friendlyRoleDone(role: AgentRoleLabel): string {
  return roleMessages[role]?.done || `${role}处理好了`
}

const stageMap: Record<string, TaskStage> = {
  QUEUED: '等待中',
  RUNNING: '处理中',
  WAITING_CONFIRM: '请确认',
  DONE: '已完成',
  FAILED: '遇到问题',
  等待中: '等待中',
  处理中: '处理中',
  请确认: '请确认',
  已完成: '已完成',
  遇到问题: '遇到问题',
}

export function friendlyStage(stage: string): TaskStage {
  return stageMap[stage] || '处理中'
}

export function friendlyStageMessage(stage: TaskStage): string {
  return stageMessages[stage]
}

export function friendlyProvider(provider: string): ProviderLabel {
  return providerLabels[provider] || '兼容接口'
}

export function friendlyError(err: unknown): string {
  if (err instanceof ApiError) {
    const code = err.body?.code || ''
    for (const [pattern, message] of friendlyErrors) {
      if (pattern.test(code)) return message
    }
    if (err.status === 400) return '提交的内容有点问题，检查一下再试'
    if (err.status >= 500) return '服务开小差了，稍后再试一次'
  }
  if (err instanceof Error) {
    for (const [pattern, message] of friendlyErrors) {
      if (pattern.test(err.message)) return message
    }
  }
  return '这一步没能完成，换个方式再试试'
}

export function friendlyFileError(): string {
  return '这个文件暂时读不出来，换一个导出文件试试'
}

export function friendlyFileSizeError(): string {
  return '这个文件有点大，换一个小一点的试试'
}

export function fileSizeText(size: number): string {
  if (size < 1024) return `${size} B`
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KB`
  return `${(size / 1024 / 1024).toFixed(1)} MB`
}
