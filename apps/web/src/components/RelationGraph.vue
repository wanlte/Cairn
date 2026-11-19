<script setup lang="ts">
import { computed } from 'vue'
import { Network } from 'lucide-vue-next'
import type { RelationGraph as Graph } from '../types'

const props = defineProps<{ graph: Graph }>()

const positions = computed(() => {
  const nodes = props.graph.nodes.slice(0, 14)
  const total = Math.max(1, nodes.length)
  return nodes.map((node, index) => {
    const angle = (index / total) * Math.PI * 2 - Math.PI / 2
    return {
      ...node,
      x: 150 + Math.cos(angle) * 105,
      y: 100 + Math.sin(angle) * 75,
    }
  })
})

const positionMap = computed(() => {
  const map = new Map<string, { x: number; y: number }>()
  positions.value.forEach((node) => map.set(node.id, { x: node.x, y: node.y }))
  return map
})

const lines = computed(() =>
  props.graph.edges
    .map((edge) => {
      const start = positionMap.value.get(edge.source)
      const end = positionMap.value.get(edge.target)
      if (!start || !end) return null
      return { ...edge, x1: start.x, y1: start.y, x2: end.x, y2: end.y }
    })
    .filter((item): item is NonNullable<typeof item> => item !== null),
)
</script>

<template>
  <section class="card animate-fade-up">
    <div class="card-head">
      <div>
        <h2 class="text-[16px] font-semibold text-ink">人和话题的关系</h2>
        <p class="mt-1 text-[12px] text-muted">同一段记录里反复一起出现的人和话题，会被连在一起。</p>
      </div>
      <span class="badge gray">{{ graph.nodes.length }} 个点</span>
    </div>

    <div v-if="!graph.nodes.length" class="empty">
      还没有可连的关系。先记一些带来源或话题的记录，再回来重建看看。
    </div>
    <template v-else>
      <svg viewBox="0 0 300 200" class="h-[240px] w-full">
        <line
          v-for="(line, index) in lines"
          :key="index"
          :x1="line.x1"
          :y1="line.y1"
          :x2="line.x2"
          :y2="line.y2"
          stroke="#c7d0e0"
          :stroke-width="Math.min(3, 0.8 + line.weight * 0.4)"
        />
        <g v-for="node in positions" :key="node.id">
          <circle
            :cx="node.x"
            :cy="node.y"
            :r="7 + Math.min(7, node.weight * 1.5)"
            :fill="node.kind === 'person' ? '#14b8a6' : '#4f46e5'"
            fill-opacity="0.85"
          />
          <text
            :x="node.x"
            :y="node.y - 13"
            text-anchor="middle"
            font-size="10"
            fill="#5b6478"
          >
            {{ node.label }}
          </text>
        </g>
      </svg>
      <div class="flex flex-wrap gap-3 text-[11px] text-muted">
        <span class="inline-flex items-center gap-1.5">
          <span class="h-2.5 w-2.5 rounded-full bg-brand" /> 话题
        </span>
        <span class="inline-flex items-center gap-1.5">
          <span class="h-2.5 w-2.5 rounded-full bg-brand-teal" /> 人
        </span>
        <span class="inline-flex items-center gap-1.5">
          <Network :size="12" /> 线越粗，一起出现得越多
        </span>
      </div>
    </template>
  </section>
</template>
