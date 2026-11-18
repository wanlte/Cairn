import type {
  AgentResult,
  ReviewDistributionEntry,
  ReviewItem,
  ReviewOverview,
  ReviewReport,
} from '../types'

export interface ReportStats {
  dialogueCount: number
  keyEvents: number
  judgments: number
  changes: number
  actions: number
  verified: number
}

export interface DistributionBar {
  label: string
  count: number
  percent: number
}

export interface TrendPoint {
  label: string
  value: number
}

export function text(payload: Record<string, unknown> | undefined | null, key: string): string {
  const value = payload?.[key]
  return typeof value === 'string' ? value.trim() : ''
}

export function overviewOf(report: ReviewReport | null | undefined): ReviewOverview {
  return report?.overview || {}
}

export function sectionItems(report: ReviewReport | null | undefined, section: string): ReviewItem[] {
  return (report?.items || []).filter((item) => item.section === section)
}

export function comparisonText(report: ReviewReport | null | undefined): string {
  return overviewOf(report).comparison_with_last_period?.trim() || ''
}

export function reportStats(report: ReviewReport | null | undefined): ReportStats {
  const overview = overviewOf(report)
  const actions = report?.action_items || []
  return {
    dialogueCount: typeof overview.dialogue_count === 'number' ? overview.dialogue_count : 0,
    keyEvents: sectionItems(report, 'key_event').length,
    judgments: sectionItems(report, 'judgment').length,
    changes: sectionItems(report, 'cognitive_change').length,
    actions: actions.length,
    verified: actions.filter((item) => item.status === 'VERIFIED').length,
  }
}

export function distributionBars(
  entries: ReviewDistributionEntry[] | undefined,
  key: 'domain' | 'topic',
  limit = 5,
): DistributionBar[] {
  const rows = (entries || [])
    .map((item) => ({ label: (item[key] || '').trim(), count: Number(item.count) || 0 }))
    .filter((item) => item.label)
    .slice(0, limit)
  const max = Math.max(1, ...rows.map((item) => item.count))
  return rows.map((item) => ({ ...item, percent: Math.round((item.count / max) * 100) }))
}

export function trendSeries(reports: ReviewReport[]): TrendPoint[] {
  return [...reports]
    .reverse()
    .slice(-8)
    .map((report) => ({
      label: report.created_at ? report.created_at.slice(5, 10).replace('-', '/') : '',
      value: Number(report.overview?.dialogue_count) || 0,
    }))
}

export function normalizeAgentResult(raw: unknown): AgentResult | null {
  if (!raw || typeof raw !== 'object') return null
  const source = raw as AgentResult & { nextLabel?: string }
  return {
    kind: source.kind || '整理',
    title: source.title || '已完成',
    summary: source.summary || '',
    suggestions: Array.isArray(source.suggestions) ? source.suggestions : [],
    next_label: source.next_label || source.nextLabel || null,
    report_id: source.report_id ?? null,
  }
}
