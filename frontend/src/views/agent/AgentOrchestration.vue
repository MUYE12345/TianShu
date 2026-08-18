<template>
  <div class="orchestration-page">
    <!-- ===== Header ===== -->
    <header class="orch-header">
      <div class="header-left">
        <div class="header-brand">
          <span class="brand-icon">O</span>
          <h1>智能体编排</h1>
        </div>
        <div class="mode-tabs">
          <button :class="['mode-tab', { active: mode === 'subagent' }]" @click="setMode('subagent')">
            主从协作
          </button>
          <button :class="['mode-tab', { active: mode === 'team' }]" @click="setMode('team')">
            平等协作
          </button>
        </div>
        <el-dropdown v-if="savedRuns.length > 0" trigger="click">
          <el-button text size="small">
            编排记录 ({{ savedRuns.filter(r => r.mode === mode).length }})
            <el-icon><ArrowDown /></el-icon>
          </el-button>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item v-for="run in savedRuns.filter(r => r.mode === mode)" :key="run.id" @click="loadSavedRun(run)">
                <div style="max-width:240px;overflow:hidden;text-overflow:ellipsis">{{ run.prompt }}</div>
                <div style="font-size:11px;color:var(--text-tertiary)">{{ run.nodes.length }} 个智能体</div>
              </el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
      </div>
      <div class="header-right">
        <span v-if="nodes.length > 0" class="node-count">{{ nodes.length }} 个智能体</span>
        <el-button size="small" :disabled="nodes.length === 0" @click="clearAll">清空</el-button>
        <el-button type="primary" size="small" :disabled="nodes.length === 0 || executing" :loading="executing" @click="handleExecute">
          ▶ 执行编排
        </el-button>
      </div>
    </header>

    <!-- ===== Body ===== -->
    <div class="orch-body">
      <!-- 左侧：智能体面板 -->
      <aside class="agent-palette">
        <div class="palette-head">
          <h3>可用智能体</h3>
          <el-tag size="small" round>{{ agents.length }}</el-tag>
        </div>
        <el-scrollbar class="palette-list">
          <div v-for="agent in agents" :key="agent.id"
               class="palette-item"
               draggable="true"
               :title="'拖拽或点击添加到画布'"
               @dragstart="onDragStart($event, agent)"
               @click="addAgentFromPalette(agent)">
            <div class="palette-avatar" :style="{ background: categoryColor(agent.category) }">
              {{ agent.name.charAt(0) }}
            </div>
            <div class="palette-info">
              <div class="palette-name">{{ agent.name }}</div>
              <div class="palette-desc">{{ agent.category }}</div>
            </div>
            <el-tag size="small" round :type="agent.enabled ? 'success' : 'info'" effect="plain">
              {{ agent.enabled ? '就绪' : '停用' }}
            </el-tag>
          </div>
          <el-empty v-if="agents.length === 0" :image-size="40" description="暂无可用智能体" />
        </el-scrollbar>
      </aside>

      <!-- 中间：画布 -->
      <div class="orch-canvas"
           @dragenter.prevent="onDragOver"
           @dragover.prevent="onDragOver"
           @dragleave="onDragLeave"
           @drop.prevent="onDrop"
           :class="{ 'canvas-over': isDragOver }">
        <!-- 会议室模式 -->
        <template v-if="mode === 'subagent'">
          <div v-if="nodes.length === 0" class="canvas-empty">
            <div class="empty-icon">🎯</div>
            <p>从左侧添加智能体</p>
            <p class="empty-hint">拖拽或点击左侧智能体 · 第一个为主智能体，其余为子智能体</p>
          </div>
          <div v-else class="subagent-layout">
            <!-- 主智能体 -->
            <div v-for="node in primaryNodes" :key="node.id" class="primary-node">
              <div class="node-card primary">
                <div class="node-badge">主智能体</div>
                <span v-if="node.status" class="node-status" :class="node.status">{{ node.status === 'running' ? '⟳' : node.status === 'done' ? '✓' : '' }}</span>
                <div class="node-avatar" :style="{ background: categoryColor(node.category) }">{{ node.name.charAt(0) }}</div>
                <div class="node-name">{{ node.name }}</div>
                <el-input v-model="node.task" placeholder="分配子任务..." size="small" />
                <el-button text type="danger" size="small" @click="removeNode(node.id)" class="node-remove">✕</el-button>
              </div>
              <div class="subagent-list">
                <div v-for="sub in subNodes" :key="sub.id" class="sub-node">
                  <div class="node-card sub">
                    <div class="node-badge sub-badge">子智能体</div>
                    <span v-if="sub.status" class="node-status" :class="sub.status">{{ sub.status === 'running' ? '⟳' : sub.status === 'done' ? '✓' : '' }}</span>
                    <div class="node-avatar" :style="{ background: categoryColor(sub.category) }">{{ sub.name.charAt(0) }}</div>
                    <div class="node-name">{{ sub.name }}</div>
                    <el-input v-model="sub.task" placeholder="职责描述..." size="small" />
                    <el-button text type="danger" size="small" @click="removeNode(sub.id)" class="node-remove">✕</el-button>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </template>

        <!-- 茶水间模式 -->
        <template v-else>
          <div v-if="nodes.length === 0" class="canvas-empty">
            <div class="empty-icon">☕</div>
            <p>拖拽智能体到此处进行群组讨论</p>
            <p class="empty-hint">至少需要 2 个智能体</p>
          </div>
          <div v-else class="team-layout">
            <div v-for="node in nodes" :key="node.id" class="team-node">
              <div class="node-card">
                <span v-if="node.status" class="node-status" :class="node.status">{{ node.status === 'running' ? '⟳' : node.status === 'done' ? '✓' : '' }}</span>
                <div class="node-avatar" :style="{ background: categoryColor(node.category) }">{{ node.name.charAt(0) }}</div>
                <div class="node-name">{{ node.name }}</div>
                <el-input v-model="node.task" placeholder="讨论职责..." size="small" />
                <el-button text type="danger" size="small" @click="removeNode(node.id)" class="node-remove">✕</el-button>
              </div>
            </div>
          </div>
        </template>
      </div>

      <!-- 右侧：执行面板 -->
      <aside class="exec-panel">
        <div class="panel-section">
          <h3>全局指令</h3>
          <el-input v-model="globalPrompt" type="textarea" :rows="3" placeholder="输入任务需求..." />
        </div>
        <div class="panel-section">
          <div style="display:flex;gap:8px">
            <el-button type="primary" :disabled="nodes.length === 0" :loading="executing" @click="handleExecute" style="flex:1">
              {{ executing ? '编排执行中...' : '▶ 开始执行' }}
            </el-button>
            <el-button v-if="executing" type="danger" plain @click="stopExecute">■ 停止</el-button>
          </div>
          <p class="simulate-hint">真实编排 · 主控规划 → 子智能体并行执行 → 汇总</p>
        </div>
        <div class="panel-section exec-log-section">
          <h3>执行日志</h3>
          <div class="exec-log">
            <div v-for="(log, i) in execLogs" :key="i" class="log-item" :class="log.type">
              <span class="log-dot" />
              <span>{{ log.msg }}</span>
            </div>
            <div v-if="execLogs.length === 0" class="log-empty">等待执行...</div>
          </div>
        </div>
        <div v-if="finalResult" class="panel-section">
          <h3>最终结果</h3>
          <div class="exec-result">{{ finalResult }}</div>
        </div>
      </aside>
    </div>
  </div>
</template>

<script>
export default { name: 'AgentOrchestration' }
</script>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { ArrowDown } from '@element-plus/icons-vue'
import request from '../../utils/request'

const mode = ref('subagent')
const agents = ref([])
const nodes = ref([])
const globalPrompt = ref('')
const isDragOver = ref(false)
const dragLeaveTimer = ref(null)
const executing = ref(false)
const abortCtrl = ref(null)
const execLogs = ref([])
const finalResult = ref('')
const savedRuns = ref([])

function onDragOver(e) {
  e.preventDefault()
  isDragOver.value = true
  if (dragLeaveTimer.value) {
    clearTimeout(dragLeaveTimer.value)
    dragLeaveTimer.value = null
  }
}

function onDragLeave() {
  // 延迟一下避免子元素 dragleave 误触
  dragLeaveTimer.value = setTimeout(() => {
    isDragOver.value = false
  }, 100)
}

// 切换模式时重置节点角色: 避免 team 模式残留的 primary/sub 身份在切回 subagent 时错乱
function setMode(m) {
  if (mode.value === m) return
  mode.value = m
  let mapped = nodes.value.map(n => ({
    ...n,
    role: m === 'subagent' ? (n.role === 'primary' ? 'primary' : 'sub') : 'member',
  }))
  // 切回主从协作但没有任何主控时, 自动把第一个节点升为主控
  if (m === 'subagent' && mapped.length > 0 && !mapped.some(n => n.role === 'primary')) {
    mapped = mapped.map((n, i) => i === 0 ? { ...n, role: 'primary' } : n)
  }
  nodes.value = mapped
}

const primaryNodes = computed(() => nodes.value.filter(n => n.role === 'primary'))
const subNodes = computed(() => nodes.value.filter(n => n.role === 'sub'))

const categoryColor = (cat) => {
  const m = { '对话': '#7c5cad', '分析': '#a17f29', '工具': '#3d8047', '数据': '#5a7bb3', '自动化': '#b85469', '通用': '#6b6b73' }
  return m[cat] || '#6b6b73'
}

onMounted(async () => {
  try {
    const res = await request.get('/api/agents')
    agents.value = (res.items || []).filter(a => a.enabled)
  } catch {}
  // 编排记录优先从后端拉取(持久化), 失败回退 localStorage(离线兜底)
  try {
    const res = await request.get('/api/teams')
    if (res?.items?.length) {
      savedRuns.value = res.items.map(t => ({
        id: 'team-' + t.id,
        mode: t.mode,
        prompt: t.prompt,
        nodes: t.nodes || [],
        name: t.name,
        createdAt: Date.parse(t.updated_at || t.created_at) || Date.now(),
      }))
      return
    }
  } catch {}
  try {
    const saved = localStorage.getItem('orch_saved')
    if (saved) savedRuns.value = JSON.parse(saved)
  } catch {}
})

// 拖拽数据兜底：dataTransfer 在某些浏览器取不到自定义类型时，用变量保底
let lastDraggedAgent = null
function onDragStart(e, agent) {
  lastDraggedAgent = agent
  try {
    const s = JSON.stringify(agent)
    e.dataTransfer.setData('text/plain', s)
    e.dataTransfer.setData('application/json', s)
    e.dataTransfer.effectAllowed = 'copy'
  } catch {}
}

function onDrop(e) {
  isDragOver.value = false
  let agent = null
  try {
    agent = JSON.parse(e.dataTransfer.getData('application/json')
                       || e.dataTransfer.getData('text/plain'))
  } catch {}
  if (!agent && lastDraggedAgent) agent = lastDraggedAgent  // dataTransfer 兜底
  if (agent) addAgentFromPalette(agent)
}

// 点击也可添加智能体（不依赖拖拽）
function addAgentFromPalette(agent) {
  if (!agent || !agent.id) return
  if (nodes.value.some(n => n.companionId === agent.id)) return
  const isFirst = nodes.value.length === 0
  nodes.value.push({
    id: `node-${Date.now()}`,
    name: agent.name,
    category: agent.category,
    companionId: agent.id,
    role: mode.value === 'subagent' ? (isFirst ? 'primary' : 'sub') : 'member',
    task: '',
  })
}

function removeNode(id) {
  nodes.value = nodes.value.filter(n => n.id !== id)
}

function clearAll() {
  nodes.value = []
  execLogs.value = []
}

function addLog(type, msg) {
  execLogs.value.push({ type, msg })
}

async function handleExecute() {
  if (nodes.value.length === 0) return
  if (mode.value === 'subagent' && primaryNodes.value.length === 0) {
    addLog('error', '请至少指定一个主智能体')
    return
  }
  if (mode.value === 'team' && nodes.value.length < 2) {
    addLog('error', '平等协作模式至少需要 2 个智能体')
    return
  }
  if (!globalPrompt.value.trim()) {
    addLog('error', '请输入全局指令')
    return
  }

  executing.value = true
  execLogs.value = []
  finalResult.value = ''
  nodes.value.forEach(n => { n.status = 'idle' })
  addLog('info', `🚀 开始 ${mode.value === 'subagent' ? '主从协作' : '平等协作'} 编排（真实执行）`)
  addLog('info', `📋 指令: ${globalPrompt.value}`)
  addLog('info', `🤖 参与: ${nodes.value.map(n => n.name).join(', ')}`)

  // 保存编排记录: 后端持久化(teams 表), localStorage 作为离线兜底
  const run = { id: `run-${Date.now()}`, mode: mode.value, prompt: globalPrompt.value, nodes: JSON.parse(JSON.stringify(nodes.value)), createdAt: Date.now() }
  savedRuns.value = [run, ...savedRuns.value].slice(0, 20)
  try { localStorage.setItem('orch_saved', JSON.stringify(savedRuns.value)) } catch {}
  try {
    // 静默持久化到后端: 失败不阻断编排执行
    await request.post('/api/teams', {
      name: (globalPrompt.value || '未命名团队').slice(0, 20),
      mode: mode.value,
      nodes: JSON.parse(JSON.stringify(nodes.value)),
      prompt: globalPrompt.value,
    })
  } catch {}

  // 真实编排：调用后端 SSE(支持手动停止)
  let doneReceived = false
  const controller = new AbortController()
  abortCtrl.value = controller
  try {
    const resp = await fetch('/api/agents/orchestrate', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        ...(localStorage.getItem('token') ? { Authorization: `Bearer ${localStorage.getItem('token')}` } : {}),
      },
      body: JSON.stringify({ task: globalPrompt.value, mode: mode.value, nodes: nodes.value }),
      signal: controller.signal,
    })
    if (!resp.ok) {
      const err = await resp.json().catch(() => ({}))
      throw new Error(err.detail || `HTTP ${resp.status}`)
    }
    const reader = resp.body.getReader()
    const decoder = new TextDecoder()
    let buf = ''
    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      buf += decoder.decode(value, { stream: true })
      const lines = buf.split('\n')
      buf = lines.pop() || ''
      for (const line of lines) {
        if (!line.startsWith('data: ')) continue
        try {
          const ev = JSON.parse(line.slice(6))
          if (ev.type === 'done') doneReceived = true
          handleEvent(ev)
        } catch {}
      }
    }
  } catch (e) {
    if (e?.name === 'AbortError') {
      addLog('warning', '⏹ 已手动停止编排')
      try {
        nodes.value.forEach(n => { if (n.status === 'running') n.status = 'idle' })
      } catch {}
    } else {
      addLog('error', '编排失败: ' + e.message)
    }
  } finally {
    abortCtrl.value = null
    if (doneReceived) addLog('success', '🎉 编排执行完成')
    else if (!execLogs.value.some(l => l.type === 'error') && !execLogs.value.some(l => l.msg.includes('已手动停止')))
      addLog('warning', '⚠️ 编排已结束（未收到完成标记）')
    executing.value = false
  }
}

function stopExecute() {
  try { abortCtrl.value?.abort() } catch {}
}

function handleEvent(ev) {
  const type = ev.type
  if (type === 'agent_turn') {
    const node = nodes.value.find(n => n.name === ev.agent)
    if (node) node.status = ev.status === 'start' ? 'running' : (ev.status === 'end' ? 'done' : node.status)
    const statusText = ev.status === 'start' ? '开始执行' : ev.status === 'end' ? '执行完成' : ev.status
    addLog(ev.status === 'end' ? 'success' : 'info', `🤖 ${ev.agent} ${statusText}`)
    if (ev.task) addLog('info', `   └ ${ev.task}`)
  } else if (type === 'plan') {
    addLog('info', `📋 主控分工: ${ev.plan}`)
  } else if (type === 'token') {
    finalResult.value += ev.text || ''
  } else if (type === 'error') {
    addLog('error', ev.message || '执行错误')
  } else if (type === 'done') {
    finalResult.value = ev.final_response || finalResult.value
  }
}

function loadSavedRun(run) {
  clearAll()
  mode.value = run.mode
  globalPrompt.value = run.prompt
  nodes.value = JSON.parse(JSON.stringify(run.nodes))
}
</script>

<style scoped>
.orchestration-page {
  display: flex; flex-direction: column; height: 100%; background: var(--bg);
}
.orch-header {
  display: flex; align-items: center; justify-content: space-between;
  padding: 0 20px; height: 56px; background: var(--bg-card);
  border-bottom: 1px solid var(--border); flex-shrink: 0;
}
.header-left { display: flex; align-items: center; gap: 16px; }
.header-brand { display: flex; align-items: center; gap: 8px; }
.brand-icon { width: 28px; height: 28px; border-radius: 8px; background: var(--text-primary); color: var(--bg-card); display: grid; place-items: center; font-size: 13px; font-weight: 700; }
.header-brand h1 { font-size: 16px; font-weight: 700; margin: 0; }
.mode-tabs { display: flex; padding: 2px; border-radius: 8px; background: var(--bg-subtle); }
.mode-tab { padding: 4px 12px; border-radius: 6px; font-size: 12px; border: none; cursor: pointer; background: transparent; color: var(--text-secondary); }
.mode-tab.active { background: var(--bg-card); color: var(--text-primary); font-weight: 600; box-shadow: 0 1px 2px rgba(0,0,0,0.06); }
.header-right { display: flex; align-items: center; gap: 8px; }
.node-count { font-size: 12px; color: var(--text-tertiary); }

/* Body */
.orch-body { display: flex; flex: 1; min-height: 0; }

/* 左侧面板 */
.agent-palette { width: 240px; background: var(--bg-card); border-right: 1px solid var(--border); display: flex; flex-direction: column; }
.palette-head { display: flex; align-items: center; justify-content: space-between; padding: 12px 14px; }
.palette-head h3 { margin: 0; font-size: 13px; font-weight: 600; }
.palette-list { flex: 1; padding: 0 8px; }
.palette-item {
  display: flex; align-items: center; gap: 8px; padding: 8px 10px; border-radius: 8px;
  cursor: grab; transition: background 0.15s; margin-bottom: 2px;
}
.palette-item:hover { background: var(--sidebar-hover); }
.palette-avatar { width: 28px; height: 28px; border-radius: 6px; display: grid; place-items: center; color: #fff; font-size: 12px; font-weight: 600; flex-shrink: 0; }
.palette-info { flex: 1; min-width: 0; }
.palette-name { font-size: 13px; font-weight: 500; }
.palette-desc { font-size: 11px; color: var(--text-tertiary); }

/* 画布 */
.orch-canvas { flex: 1; padding: 20px; overflow-y: auto; min-height: 0; }
.canvas-over { background: var(--primary-light); }
.canvas-empty { display: flex; flex-direction: column; align-items: center; justify-content: center; height: 100%; color: var(--text-tertiary); }
.canvas-empty .empty-icon { font-size: 40px; margin-bottom: 8px; }
.canvas-empty p { margin: 0; font-size: 14px; }
.canvas-empty .empty-hint { font-size: 12px; margin-top: 4px; }
.subagent-layout { display: flex; flex-direction: column; gap: 16px; }
.team-layout { display: flex; flex-wrap: wrap; gap: 12px; }

/* 节点卡片 */
.node-card { position: relative; border: 1px solid var(--border); border-radius: 12px; padding: 14px; background: var(--bg-card); display: flex; flex-direction: column; align-items: center; gap: 8px; min-width: 160px; }
.node-card.primary { border-color: var(--tz-purple); background: var(--tz-purple-soft); }
.node-card.sub { border-color: var(--tz-yellow); background: var(--tz-yellow-soft); border-style: dashed; }
.node-badge { font-size: 10px; font-weight: 600; padding: 2px 8px; border-radius: 999px; background: var(--tz-purple); color: #fff; }
.node-badge.sub-badge { background: var(--tz-yellow); }
.node-avatar { width: 36px; height: 36px; border-radius: 10px; display: grid; place-items: center; color: #fff; font-size: 14px; font-weight: 600; }
.node-status {
  position: absolute; top: 6px; right: 6px; width: 20px; height: 20px; border-radius: 50%;
  display: grid; place-items: center; font-size: 12px; color: #fff; z-index: 2;
}
.node-status.running { background: var(--tz-blue); animation: pulse 1.4s infinite; }
.node-status.done { background: var(--tz-green); }
.node-name { font-size: 14px; font-weight: 600; }
.node-remove { position: absolute; top: 4px; right: 4px; }
.subagent-list { display: flex; gap: 12px; flex-wrap: wrap; margin-top: 8px; padding-left: 24px; border-left: 2px dashed #d1d5db; }
.team-node { }
.primary-node { }

/* 执行面板 */
.exec-panel { width: 280px; background: var(--bg-card); border-left: 1px solid var(--border); display: flex; flex-direction: column; padding: 14px; gap: 12px; }
.panel-section h3 { margin: 0 0 8px; font-size: 12px; font-weight: 600; color: var(--text-tertiary); text-transform: uppercase; letter-spacing: 0.5px; }
.exec-log-section { flex: 1; overflow: hidden; display: flex; flex-direction: column; }
.exec-log { flex: 1; overflow-y: auto; font-size: 12px; }
.log-item { display: flex; align-items: flex-start; gap: 6px; padding: 4px 0; }
.log-dot { width: 6px; height: 6px; border-radius: 50%; margin-top: 4px; flex-shrink: 0; }
.log-item.info .log-dot { background: #3b82f6; }
.log-item.success .log-dot { background: #10b981; }
.log-item.error .log-dot { background: #ef4444; }
.log-empty { color: var(--text-tertiary); padding: 12px 0; text-align: center; }

/* 暗色适配 */
html.dark .node-card.primary { background: var(--tz-purple-soft); }
html.dark .node-card.sub { background: var(--tz-yellow-soft); border-color: var(--tz-yellow); }
html.dark .node-badge { background: var(--tz-purple); }
html.dark .node-badge.sub-badge { background: var(--tz-yellow); }

.simulate-hint {
  font-size: 11px;
  color: var(--text-tertiary);
  text-align: center;
  margin: 6px 0 0;
}
.exec-result {
  font-size: 12px; line-height: 1.7; color: var(--text-secondary);
  background: var(--bg-subtle); border-radius: 10px; padding: 10px 12px;
  white-space: pre-wrap; max-height: 220px; overflow-y: auto;
}
</style>
