<template>
  <div class="kg-wrap">
    <div v-loading="loading" class="kg-canvas">
      <VChart v-if="hasData" :option="option" autoresize style="width:100%;height:100%" @click="onClick" />
      <div v-else-if="!loading" class="kg-empty">
        <div class="kg-empty-icon">🕸</div>
        <p>知识图谱还是空的</p>
        <p class="kg-empty-sub">在笔记正文中用 <code>[[笔记标题]]</code> 引用其他页面，保存后就会在这里形成关联图。</p>
      </div>
    </div>
  </div>
</template>

<script>
export default { name: 'KnowledgeGraph' }
</script>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import axios from 'axios'
import { use } from 'echarts/core'
import { CanvasRenderer } from 'echarts/renderers'
import { GraphChart } from 'echarts/charts'
import { TooltipComponent } from 'echarts/components'
import VChart from 'vue-echarts'

use([CanvasRenderer, GraphChart, TooltipComponent])

const router = useRouter()
const loading = ref(true)
const nodes = ref([])
const edges = ref([])

const hasData = computed(() => nodes.value.length > 0)

const option = computed(() => {
  const colorPalette = [
    '#8aa6cf', '#ec8da0', '#eccb6a', '#a78bcf', '#84c98c', '#e8a33d', '#6a5ae0',
  ]
  return {
    tooltip: {
      trigger: 'item',
      formatter: p => `<b>${p.data.name || p.name}</b><br/>${p.dataType === 'edge' ? '' : '点击进入页面'}`,
    },
    animationDurationUpdate: 700,
    series: [{
      type: 'graph',
      layout: 'force',
      roam: true,
      draggable: true,
      data: nodes.value.map((n, i) => ({
        id: n.id,
        name: n.label || n.id,
        symbolSize: 26,
        itemStyle: { color: colorPalette[i % colorPalette.length] },
      })),
      links: edges.value.map(e => ({ source: e.source, target: e.target })),
      categories: [],
      force: {
        repulsion: 240,
        edgeLength: [70, 140],
        gravity: 0.12,
      },
      label: { show: true, position: 'right', fontSize: 12, color: 'var(--text-secondary, #6b6b73)' },
      lineStyle: { color: '#c9c8d0', width: 1.3, curveness: 0.12, opacity: 0.6 },
      emphasis: {
        focus: 'adjacency',
        lineStyle: { width: 2.2, opacity: 0.9 },
      },
    }],
  }
})

function onClick(params) {
  if (params.dataType !== 'node') return
  const id = params.data?.id
  if (id) router.push('/wiki/' + id)
}

onMounted(async () => {
  try {
    const { data } = await axios.get('/api/wiki/graph')
    nodes.value = data?.nodes || []
    edges.value = data?.edges || []
  } catch {
    nodes.value = []
    edges.value = []
  }
  loading.value = false
})
</script>

<style scoped>
.kg-wrap { height: 520px; }
.kg-canvas { height: 100%; border: 1px solid var(--border-light); border-radius: 18px; background: var(--bg-card); overflow: hidden; }
.kg-empty { height: 100%; display: flex; flex-direction: column; align-items: center; justify-content: center; color: var(--text-tertiary); }
.kg-empty-icon { font-size: 40px; margin-bottom: 10px; }
.kg-empty p { margin: 0 0 6px; font-size: 13px; font-weight: 600; }
.kg-empty-sub { font-weight: 400 !important; color: var(--text-muted); max-width: 320px; text-align: center; line-height: 1.7; }
.kg-empty-sub code { background: var(--md-code-bg); color: var(--md-code-color); padding: 1px 6px; border-radius: 5px; font-family: var(--font-mono); font-size: 12px; }
</style>
