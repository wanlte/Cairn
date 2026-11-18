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

export function friendlyAuthError(err: unknown, mode: 'login' | 'register'): string {
  if (err instanceof ApiError) {
    const code = err.body?.code || ''
    if (code === 'EMAIL_EXISTS' || err.status === 409) return '这个邮箱已经注册过了，直接登录就好'
    if (code === 'VALIDATION_ERROR' || err.status === 422) return '密码至少要 8 位，换一个长一点的试试'
    if (code === 'INVALID_CREDENTIALS' || (err.status === 401 && mode === 'login')) return '邮箱或密码不对，再检查一下'
  }
  return mode === 'register' ? '这次没注册成功，换个邮箱或密码再试' : '这次没能登录，稍后再试一次'
}

export function friendlyFileError(): string {
  return '这个文件暂时读不出来，换一个导出文件试试'
}

export function friendlyFileSizeError(): string {
  return '这个文件有点大，换一个小一点的试试'
}

const verdictLabels: Record<string, string> = {
  CORRECT: '判断对了',
  PARTIAL: '有对有偏',
  WRONG: '这次看偏了',
  UNVERIFIED: '还待验证',
}

const attributionLabels: Record<string, string> = {
  NONE: '没有特别的原因',
  KNOWLEDGE_GAP: '当时还缺这块知识',
  VERIFICATION_MISSING: '少了验证这一步',
  ASSUMPTION_WRONG: '前提假设不成立',
  TIME_PRESSURE: '时间太赶',
  COMMUNICATION: '沟通没对齐',
}

const actionStatusLabels: Record<string, string> = {
  PENDING: '还没开始',
  VERIFIED: '已经做到',
  REOPENED: '重新打开',
}

export function friendlyVerdict(verdict?: string | null): string {
  return verdictLabels[verdict || ''] || '还待验证'
}

export function verdictTone(verdict?: string | null): string {
  if (verdict === 'CORRECT') return 'bg-teal-50 text-[#0f766e]'
  if (verdict === 'PARTIAL') return 'bg-[#fff5e6] text-[#b45309]'
  if (verdict === 'WRONG') return 'bg-red-50 text-[#b42318]'
  return 'bg-[#f1f4f9] text-[#667085]'
}

export function friendlyAttribution(attribution?: string | null): string {
  const label = attributionLabels[attribution || '']
  return label || ''
}

export function friendlyActionStatus(status?: string | null): string {
  return actionStatusLabels[status || ''] || '还没开始'
}

export function actionStatusTone(status?: string | null): string {
  if (status === 'VERIFIED') return 'bg-teal-50 text-[#0f766e]'
  if (status === 'REOPENED') return 'bg-[#fff5e6] text-[#b45309]'
  return 'bg-[#f1f4f9] text-[#667085]'
}

export function friendlyReportStatus(status?: string | null): string {
  if (status === 'DONE') return '已完成'
  if (status === 'FAILED') return '这次没写成'
  return '还在整理'
}

export function friendlyDate(iso?: string | null): string {
  if (!iso) return ''
  const date = new Date(iso)
  if (Number.isNaN(date.getTime())) return ''
  return `${date.getFullYear()} 年 ${date.getMonth() + 1} 月 ${date.getDate()} 日`
}

export function fileSizeText(size: number): string {
  if (size < 1024) return `${size} B`
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KB`
  return `${(size / 1024 / 1024).toFixed(1)} MB`
}
