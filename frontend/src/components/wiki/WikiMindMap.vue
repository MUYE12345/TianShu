<template>
  <div class="wmm-wrap">
    <div v-loading="loading" class="wmm-canvas">
      <VChart v-if="hasData" :option="option" autoresize style="width:100%;height:100%" @click="onClick" />
      <div v-else-if="!loading" class="wmm-empty">
        <div class="wmm-empty-icon">🧠</div>
        <p>知识库还没有内容，先上传一篇文章解析成 wiki 吧</p>
      </div>
    </div>
  </div>
</template>

<script>
export default { name: 'WikiMindMap' }
</script>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import axios from 'axios'
import { use } from 'echarts/core'
import { CanvasRenderer } from 'echarts/renderers'
import { TreeChart } from 'echarts/charts'
import { TooltipComponent } from 'echarts/components'
import VChart from 'vue-echarts'

use([CanvasRenderer, TreeChart, TooltipComponent])

const router = useRouter()
const loading = ref(true)
const pages = ref([])
const edges = ref([])

const hasData = computed(() => pages.value.length > 0)

// 从 wiki 页 + 图谱边构建思维导图树
const treeData = computed(() => {
  const bySlug = {}
  pages.value.forEach(p => { bySlug[p.slug] = p })
  const childrenMap = {}
  const hasParent = new Set()
  edges.value.forEach(e => {
    if (bySlug[e.source] && bySlug[e.target] && e.source !== e.target) {
      if (!childrenMap[e.source]) childrenMap[e.source] = []
      if (!childrenMap[e.source].includes(e.target)) childrenMap[e.source].push(e.target)
      hasParent.add(e.target)
    }
  })

  // 根节点：来源页优先（上传解析的文章），其次是没有被引用的页
  const seen = new Set()
  const roots = pages.value
    .filter(p => p.type === 'source')                                    // 文章根
    .concat(pages.value.filter(p => p.type !== 'source' && !hasParent.has(p.slug)))
    .filter(p => !seen.has(p.slug) && seen.add(p.slug))
    .slice(0, 40)
  if (roots.length === 0 && pages.value.length) roots.push(pages.value[0])

  const visited = new Set()
  function makeNode(slug, depth) {
    if (visited.has(slug)) return null
    visited.add(slug)
    const p = bySlug[slug]
    const node = { name: p ? p.title : slug, slug, type: p ? p.type : '' }
    if (depth < 2) {
      const kids = (childrenMap[slug] || []).filter(c => c !== slug)
      const childNodes = kids.map(k => makeNode(k, depth + 1)).filter(Boolean)
      if (childNodes.length) node.children = childNodes
    }
    visited.delete(slug)
    return node
  }

  return { name: 'Wiki 知识库', children: roots.map(r => makeNode(r.slug, 1)) }
})

const option = computed(() => ({
  tooltip: { trigger: 'item' },
  series: [{
    type: 'tree',
    data: [treeData.value],
    layout: 'radial',
    symbol: 'circle',
    symbolSize: 8,
    edgeShape: 'curve',
    edgeForkPosition: '40%',
    initialTreeDepth: 3,
    expandAndCollapse: true,
    roam: true,
    leaves: { label: { position: 'right', rotate: 0, verticalAlign: 'middle' } },
    label: { fontSize: 12, color: 'var(--text-secondary, #4d4d54)', position: 'left' },
    itemStyle: { color: '#8aa6cf' },
    lineStyle: { color: 'var(--border-input, #c9c8d0)', width: 1.2, curveness: 0.5 },
    emphasis: { focus: 'descendant', label: { color: 'var(--text-primary, #1a1a1a)', fontWeight: 600 } },
  }],
}))

function onClick(params) {
  if (params.data && params.data.slug) router.push('/wiki/' + params.data.slug)
}

onMounted(async () => {
  try {
    const [pg, gr] = await Promise.all([
      axios.get('/api/wiki/pages'),
      axios.get('/api/wiki/graph'),
    ])
    pages.value = pg.data?.items || []
    edges.value = gr.data?.edges || []
  } catch { /* 静默 */ }
  loading.value = false
})
</script>

<style scoped>
.wmm-wrap { height: 560px; }
.wmm-canvas { height: 100%; border: 1px solid var(--border-light); border-radius: 18px; background: var(--bg-card); overflow: hidden; }
.wmm-empty { height: 100%; display: flex; flex-direction: column; align-items: center; justify-content: center; color: var(--text-tertiary); }
.wmm-empty-icon { font-size: 42px; margin-bottom: 10px; }
.wmm-empty p { font-size: 13px; }
</style>
