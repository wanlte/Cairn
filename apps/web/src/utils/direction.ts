import type { DirectionKey, DirectionOption, UploadFileState } from '../types'

export const DIRECTION_OPTIONS: DirectionOption[] = [
  {
    key: 'weekly',
    label: '本周复盘',
    description: '看看这一周有哪些收获和卡点',
    prompt: '把这段时间的对话整理成一次复盘：有哪些进展、卡点、判断变化，以及下一步可以先做什么。',
  },
  {
    key: 'project',
    label: '项目复盘',
    description: '把一个项目的来龙去脉梳理清楚',
    prompt: '围绕这个项目梳理背景、关键决策、实际结果和遗留问题，帮我看清哪里走得顺、哪里需要调整。',
  },
  {
    key: 'conversation',
    label: '对话复盘',
    description: '从一段对话里提炼关键结论',
    prompt: '从这段对话里提炼关键结论、当时的判断和后来发生的结果，指出还待验证的地方。',
  },
  {
    key: 'growth',
    label: '成长画像',
    description: '更新你对自己的认识',
    prompt: '根据这些对话更新我的成长画像：关注方向、思考习惯、常见坑和正在出现的成长信号。',
  },
  {
    key: 'free',
    label: '自由提问',
    description: '带着具体问题问一问',
    prompt: '直接回答我的问题，尽量引用对话里的依据；证据不够时明确告诉我。',
  },
]

export function directionPrompt(key: DirectionKey): string {
  return DIRECTION_OPTIONS.find((item) => item.key === key)?.prompt || ''
}

export const DIRECTION_LABELS: Record<DirectionKey, string> = {
  weekly: '本周复盘',
  project: '项目复盘',
  conversation: '对话复盘',
  growth: '成长画像',
  free: '自由提问',
}

const keywordRules: Array<{ key: DirectionKey; words: string[] }> = [
  { key: 'weekly', words: ['本周', '这周', '一周', '周报', 'weekly', '周复盘', '日报'] },
  { key: 'project', words: ['项目', '迭代', '上线', '需求', '发布', '版本', 'project', '方案'] },
  { key: 'growth', words: ['画像', '成长', '职业', '规划', '优势', '短板', 'profile'] },
  { key: 'conversation', words: ['对话', '聊天', '会话', '访谈', 'chat', '交流'] },
]

export interface DirectionRecommendation {
  key: DirectionKey
  reason: string
}

export function recommendDirection(
  files: UploadFileState[],
  userText: string,
): DirectionRecommendation {
  const source = `${userText} ${files.map((file) => file.name).join(' ')}`.toLowerCase()
  let best: DirectionKey | null = null
  let bestScore = 0

  for (const rule of keywordRules) {
    let score = 0
    for (const word of rule.words) {
      if (source.includes(word.toLowerCase())) score += 1
    }
    if (score > bestScore) {
      bestScore = score
      best = rule.key
    }
  }

  if (!best || bestScore === 0) {
    if (files.length > 0) {
      return { key: 'conversation', reason: '看到你带了对话文件，先从对话里帮你提炼重点' }
    }
    return { key: 'free', reason: '还不确定方向，你可以直接说说想了解什么' }
  }

  const reasons: Record<DirectionKey, string> = {
    weekly: '看起来你想回顾这一段的进展，本周复盘挺合适',
    project: '像是围绕某个项目在梳理，项目复盘会更聚焦',
    growth: '你想更了解自己的成长轨迹，成长画像能帮上忙',
    conversation: '看到对话相关的内容，对话复盘比较合适',
    free: '你可以直接说说想了解什么',
  }
  return { key: best, reason: reasons[best] }
}
