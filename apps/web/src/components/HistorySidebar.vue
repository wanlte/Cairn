<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import {
  Archive,
  ArchiveRestore,
  Check,
  Inbox,
  LoaderCircle,
  Pin,
  Settings2,
  Trash2,
  X,
} from 'lucide-vue-next'
import { workspace } from '../stores/workspace'
import type { WorkspaceTaskResponse } from '../api/client'
import DeleteConfirmDialog from './DeleteConfirmDialog.vue'

const props = withDefaults(defineProps<{ inline?: boolean }>(), { inline: false })

const open = ref(false)
const panelVisible = computed(() => props.inline || open.value)
const tidyMode = ref(false)
const selected = ref<string[]>([])
const deleteTarget = ref<WorkspaceTaskResponse | null>(null)
const deleting = ref(false)

const history = computed(() => workspace.state.history)
const isArchived = computed(() => workspace.state.historyArchived)

function titleOf(task: WorkspaceTaskResponse): string {
  const text = (task.user_message || '').trim()
  if (!text) return '一次对话'
  return text.length > 24 ? `${text.slice(0, 24)}…` : text
}

function timeOf(value?: string | null): string {
  if (!value) return ''
  const date = new Date(value)
  return `${date.getMonth() + 1}/${date.getDate()} ${String(date.getHours()).padStart(2, '0')}:${String(date.getMinutes()).padStart(2, '0')}`
}

function kindOf(task: WorkspaceTaskResponse): string {
  return task.intent === 'free' ? '聊天' : task.intent === 'growth' ? '画像' : '复盘'
}

function toggleSidebar(): void {
  open.value = !open.value
  if (open.value) void workspace.loadHistory()
}

onMounted(() => {
  if (props.inline) void workspace.loadHistory()
})

watch(
  () => workspace.state.taskId,
  () => {
    if (props.inline) void workspace.loadHistory()
  },
)

function switchView(archived: boolean): void {
  selected.value = []
  tidyMode.value = false
  workspace.setHistoryArchived(archived)
}

function pick(task: WorkspaceTaskResponse): void {
  if (tidyMode.value) {
    toggleSelect(task.task_id)
    return
  }
  if (task.stage === 'WAITING_CONFIRM') {
    workspace.notify('这次还在等你确认，先确认后再回来', 'info')
  }
  void workspace.openTask(task.task_id)
}

function toggleSelect(taskId: string): void {
  const index = selected.value.indexOf(taskId)
  if (index >= 0) selected.value.splice(index, 1)
  else selected.value.push(taskId)
}

async function applyTidy(archived: boolean): Promise<void> {
  await workspace.tidyHistory(selected.value, archived)
  selected.value = []
  tidyMode.value = false
}

function exitTidy(): void {
  tidyMode.value = false
  selected.value = []
}

async function confirmDelete(keepProfile: boolean): Promise<void> {
  if (!deleteTarget.value) return
  deleting.value = true
  const target = deleteTarget.value
  try {
    const result = await workspace.removeTask(target.task_id, keepProfile)
    const suffix = result.profile_claims_removed
      ? `，同时清掉了 ${result.profile_claims_removed} 条画像结论`
      : keepProfile ? '，画像保留着' : ''
    workspace.notify(`对话已删除${suffix}`, 'success')
    deleteTarget.value = null
  } finally {
    deleting.value = false
  }
}
</script>

<template>
  <div class="history-root" :class="inline ? 'history-root-inline' : ''">
    <button
      v-if="!inline"
      type="button"
      class="history-toggle"
      :class="open ? 'active' : ''"
      @click="toggleSidebar"
    >
      <Archive :size="15" />
      <span>历史</span>
    </button>

    <aside v-if="panelVisible" class="history-panel" :class="inline ? 'inline' : ''">
      <div class="flex items-center justify-between border-b border-[#eef0f6] px-4 py-3">
        <div>
          <p class="text-[14px] font-semibold text-ink">历史对话</p>
          <p class="mt-0.5 text-[11px] text-muted">随时回来，接着往下聊</p>
        </div>
        <button v-if="!inline" type="button" class="icon-btn" aria-label="收起历史栏" @click="open = false">
          <X :size="15" />
        </button>
      </div>

      <div class="flex items-center gap-1 px-3 py-2">
        <button
          type="button"
          class="view-tab"
          :class="!isArchived ? 'active' : ''"
          @click="switchView(false)"
        >
          <Inbox :size="12" /> 进行中
        </button>
        <button
          type="button"
          class="view-tab"
          :class="isArchived ? 'active' : ''"
          @click="switchView(true)"
        >
          <Archive :size="12" /> 归档
        </button>
        <button
          type="button"
          class="ml-auto flex items-center gap-1 rounded-full px-2 py-1 text-[11px] font-medium transition"
          :class="tidyMode ? 'bg-brand/10 text-brand' : 'text-[#8b93a7] hover:text-ink'"
          @click="tidyMode = !tidyMode; selected = []"
        >
          <Settings2 :size="12" /> {{ tidyMode ? '整理中' : '整理' }}
        </button>
      </div>

      <div v-if="tidyMode" class="flex items-center gap-2 border-y border-[#eef0f6] bg-[#f8fafc] px-4 py-2">
        <button type="button" class="mini-btn" :disabled="!selected.length" @click="applyTidy(!isArchived)">
          <Check :size="12" /> {{ isArchived ? '恢复所选' : '归档所选' }}
        </button>
        <span class="text-[11px] text-muted">已选 {{ selected.length }} 条</span>
        <button type="button" class="ml-auto text-[11px] text-muted hover:text-ink" @click="exitTidy">取消</button>
      </div>

      <div class="min-h-0 flex-1 overflow-y-auto px-2 py-2">
        <div v-if="workspace.state.historyLoading" class="flex items-center gap-2 px-2 py-8 text-[12px] text-muted">
          <LoaderCircle :size="14" class="animate-spin text-brand" /> 正在翻找…
        </div>
        <div v-else-if="!history.length" class="px-3 py-10 text-center text-[12px] leading-relaxed text-muted">
          {{ isArchived ? '归档还是空的。整理时把不常用的对话放进来。' : '还没有历史对话，聊过几次后就会出现在这里。' }}
        </div>
        <div
          v-else
          v-for="task in history"
          :key="task.task_id"
          class="history-item"
          :class="tidyMode && selected.includes(task.task_id) ? 'selected' : ''"
          @click="pick(task)"
        >
          <button
            v-if="tidyMode"
            type="button"
            class="flex h-4 w-4 shrink-0 items-center justify-center rounded-full border"
            :class="selected.includes(task.task_id) ? 'border-brand bg-brand text-white' : 'border-[#cfd5e2]'"
            @click.stop="toggleSelect(task.task_id)"
          >
            <Check v-if="selected.includes(task.task_id)" :size="10" />
          </button>
          <div class="min-w-0 flex-1">
            <p class="truncate text-[12px] font-medium text-ink">{{ titleOf(task) }}</p>
            <div class="mt-1 flex items-center gap-1.5 text-[10px] text-muted">
              <span>{{ timeOf(task.created_at) }}</span>
              <span class="rounded-full bg-[#eef0ff] px-1.5 py-0.5 text-brand">{{ kindOf(task) }}</span>
              <span v-if="task.pinned" class="flex items-center gap-0.5 text-[#b45309]"><Pin :size="9" /> 置顶</span>
              <span v-if="task.archived" class="text-muted">已归档</span>
              <span v-else-if="task.stage === 'DONE'" class="text-[#0f766e]">已完成</span>
            </div>
          </div>
          <div v-if="!tidyMode" class="flex shrink-0 items-center gap-0.5">
            <button
              type="button"
              class="icon-btn small"
              :title="task.pinned ? '取消置顶' : '置顶这次对话'"
              @click.stop="workspace.togglePin(task.task_id)"
            >
              <Pin :size="13" :class="task.pinned ? 'text-[#b45309]' : ''" :fill="task.pinned ? 'currentColor' : 'none'" />
            </button>
            <button
              type="button"
              class="icon-btn small"
              :title="task.archived ? '恢复对话' : '归档对话'"
              @click.stop="task.archived ? workspace.archiveTask(task.task_id, false) : workspace.archiveTask(task.task_id, true)"
            >
              <ArchiveRestore v-if="task.archived" :size="13" />
              <Archive v-else :size="13" />
            </button>
            <button
              type="button"
              class="icon-btn small delete"
              title="删除这条对话"
              @click.stop="deleteTarget = task"
            >
              <Trash2 :size="13" />
            </button>
          </div>
        </div>
      </div>
    </aside>

    <DeleteConfirmDialog
      :open="Boolean(deleteTarget)"
      title="删除这条对话？"
      :description="`「${deleteTarget ? (deleteTarget.user_message || '一次对话').slice(0, 24) : ''}」删除后无法恢复，请确认下面画像的处理方式。`"
      :busy="deleting"
      @close="deleteTarget = null"
      @confirm="confirmDelete"
    />
  </div>
</template>

<style scoped>
.history-root { position: relative; }
.history-toggle {
  display: flex; align-items: center; gap: 6px;
  border-radius: 999px; border: 1px solid #e4e8f0; background: #fff;
  padding: 7px 13px; font-size: 12px; font-weight: 600; color: #5b6478;
  box-shadow: 0 1px 3px rgba(23,32,51,.04); transition: all .2s;
}
.history-toggle:hover, .history-toggle.active { border-color: rgba(79,70,229,.35); color: #4F46E5; }
.icon-btn {
  display: flex; height: 26px; width: 26px; align-items: center; justify-content: center;
  border-radius: 8px; color: #9aa2b4; transition: background .15s, color .15s;
}
.icon-btn:hover { background: #f4f6fa; color: #172033; }
.icon-btn.small { height: 24px; width: 24px; }
.icon-btn.delete:hover { background: #fef2f2; color: #b42318; }
.view-tab {
  display: flex; align-items: center; gap: 4px; border-radius: 999px;
  padding: 4px 10px; font-size: 11px; font-weight: 600; color: #8b93a7; transition: all .2s;
}
.view-tab.active { background: #fff; color: #4F46E5; box-shadow: 0 1px 2px rgba(23,32,51,.06); }
.mini-btn {
  display: flex; align-items: center; gap: 4px; border-radius: 999px;
  background: #4F46E5; padding: 4px 10px; font-size: 11px; font-weight: 600; color: #fff;
}
.mini-btn:disabled { opacity: .4; }
.history-item {
  display: flex; align-items: center; gap: 8px; cursor: pointer;
  border-radius: 12px; padding: 10px 10px; transition: background .15s;
}
.history-item:hover { background: #f7f8fc; }
.history-item.selected { background: rgba(79,70,229,.08); }
.history-panel {
  position: absolute; left: 0; top: 44px; z-index: 45;
  display: flex; height: 520px; max-height: 70vh; width: 320px; max-width: 88vw;
  flex-direction: column; overflow: hidden;
  border: 1px solid #e4e8f0; border-radius: 16px; background: #fff;
  box-shadow: 0 18px 50px rgba(23,32,51,.16); animation: fade-up .2s ease;
}
.history-root-inline { height: 100%; min-height: 0; }
.history-panel.inline {
  position: static; z-index: auto; width: 100%; height: 100%; max-height: none;
  border-color: rgba(228,232,240,.8); box-shadow: 0 8px 24px rgba(23,32,51,.05);
}
@keyframes fade-up { from { opacity: 0; transform: translateY(6px); } to { opacity: 1; transform: translateY(0); } }
</style>
