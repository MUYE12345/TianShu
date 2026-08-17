<template>
  <div class="scheduler-page">
    <!-- ===== 页头（与知识库页同款设计语言） ===== -->
    <header class="kb-top">
      <div>
        <h1 class="kb-title">定时任务</h1>
        <p class="kb-desc">创建定时任务，到时间自动执行——AI 自动生成 Cron 表达式，到点自动运行你的提示词</p>
      </div>
      <button class="btn-primary" @click="showCreate = true">＋ 新建任务</button>
    </header>

    <!-- ===== 任务总览 banner ===== -->
    <section class="all-tasks">
      <div class="all-tasks-text">
        <div class="all-tasks-title">任务总览</div>
        <div class="all-tasks-desc">支持一次、每天、工作日、每周、每月五种频次，到点自动执行，无需值守。</div>
        <div class="all-tasks-meta">共 {{ tasks.length }} 个任务 · {{ pendingCount }} 待执行 · {{ runningCount }} 运行中 · {{ doneCount }} 已完成 · {{ failedCount }} 失败</div>
      </div>
      <div class="all-tasks-icons">
        <span class="ft-clock">⏰</span>
        <span class="ft-alarm">🕐</span>
        <span class="ft-repeat">🔁</span>
        <span class="ft-cal">📅</span>
      </div>
    </section>

    <!-- ===== 任务列表 ===== -->
    <section class="task-section" v-loading="loading">
      <div class="topic-bar">
        <span class="topic-label">全部任务</span>
        <div class="status-tabs">
          <el-radio-group v-model="statusFilter" size="small">
            <el-radio-button value="all">全部 ({{ tasks.length }})</el-radio-button>
            <el-radio-button value="pending">待执行 ({{ pendingCount }})</el-radio-button>
            <el-radio-button value="running">运行中 ({{ runningCount }})</el-radio-button>
            <el-radio-button value="done">已完成 ({{ doneCount }})</el-radio-button>
            <el-radio-button value="failed">失败 ({{ failedCount }})</el-radio-button>
          </el-radio-group>
        </div>
      </div>

      <!-- 空状态：emoji + 文案 + CTA -->
      <div v-if="!loading && filteredTasks.length === 0" class="task-empty">
        <div class="task-empty-emoji">⏰</div>
        <div class="task-empty-text">还没有定时任务，创建一个让 AI 按时开工吧</div>
        <button class="btn-primary" @click="showCreate = true">＋ 新建任务</button>
      </div>

      <!-- 任务卡片网格 -->
      <div v-else class="task-grid">
        <div v-for="task in filteredTasks" :key="task.id" class="task-card" :class="'st-' + (task.status || 'pending')">
          <div class="task-card-top">
            <span class="cron-chip" :title="task.cron">{{ task.cron || '暂无 cron' }}</span>
            <el-tag :type="statusTag(task.status)" size="small" effect="plain" round>
              {{ statusLabel(task.status) }}
            </el-tag>
          </div>
          <div class="task-time">
            <span class="time-value">{{ formatTime(task) }}</span>
            <span class="time-label">{{ task.label || '' }}</span>
          </div>
          <div class="task-prompt" :title="task.prompt">{{ task.prompt }}</div>
          <div class="task-meta">
            <span class="meta-item">📅 创建于 {{ formatDate(task.createdAt) }}</span>
            <span v-if="task.lastFiredAt" class="meta-item">▶ 上次运行 {{ relativeTime(task.lastFiredAt) }}</span>
          </div>
          <div class="task-actions">
            <button class="btn-ghost run-btn" @click="runTask(task)">▶ 运行</button>
            <el-popconfirm title="确认删除？" @confirm="deleteTask(task.id)">
              <template #reference>
                <el-button text size="small" type="danger" class="del-btn">✕ 删除</el-button>
              </template>
            </el-popconfirm>
          </div>
        </div>
      </div>
    </section>

    <!-- 新建任务弹窗 -->
    <el-dialog v-model="showCreate" title="新建定时任务" width="520px" :close-on-click-modal="false">
      <el-form label-position="top">
        <el-form-item label="任务描述">
          <el-input v-model="form.prompt" type="textarea" :rows="3"
            placeholder="例如：每天早上9点查询天气并推送到飞书" />
        </el-form-item>

        <!-- 频次选择 -->
        <el-form-item label="执行频次">
          <div class="freq-tabs">
            <el-radio-group v-model="form.freq" size="small">
              <el-radio-button value="once">一次</el-radio-button>
              <el-radio-button value="daily">每天</el-radio-button>
              <el-radio-button value="weekdays">工作日</el-radio-button>
              <el-radio-button value="weekly">每周</el-radio-button>
              <el-radio-button value="monthly">每月</el-radio-button>
            </el-radio-group>
          </div>
        </el-form-item>

        <!-- 星期选择（每周/工作日） -->
        <el-form-item v-if="form.freq === 'weekly'" label="选择星期">
          <div class="weekday-pills">
            <div v-for="(d, i) in weekDays" :key="i"
              class="day-pill" :class="{ active: form.weekdays.includes(i) }"
              @click="toggleDay(i)">{{ d }}</div>
          </div>
        </el-form-item>

        <!-- 日期选择（每月） -->
        <el-form-item v-if="form.freq === 'monthly'" label="选择日期">
          <el-select v-model="form.monthDay" style="width:100%">
            <el-option v-for="d in 31" :key="d" :label="d + ' 日'" :value="d" />
          </el-select>
        </el-form-item>

        <!-- 时间（精确到分钟） -->
        <el-form-item label="执行时间">
          <el-time-picker v-model="form.time" format="HH:mm" value-format="HH:mm"
            :disabled-hours="disabledHours" placeholder="选择时间" style="width:100%" />
        </el-form-item>

        <!-- 一次性任务的日期 -->
        <el-form-item v-if="form.freq === 'once'" label="执行日期">
          <el-date-picker v-model="form.onceDate" type="date" :disabled-date="disabledDate"
            placeholder="选择日期" style="width:100%" />
        </el-form-item>

        <!-- AI 生成的 cron 预览 -->
        <el-form-item v-if="cronPreview" label="Cron 表达式（AI 自动生成）">
          <el-input :model-value="cronPreview" readonly>
            <template #append>
              <el-tag size="small" type="info">AI 生成</el-tag>
            </template>
          </el-input>
        </el-form-item>
      </el-form>

      <template #footer>
        <el-button @click="showCreate = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="submitTask">创建任务</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, computed, watch } from 'vue'
import { Plus } from '@element-plus/icons-vue'
import axios from 'axios'

// 数据
const tasks = ref([])
const loading = ref(false)
const showCreate = ref(false)
const saving = ref(false)
const statusFilter = ref('all')
const runningId = ref(null)

// 星期
const weekDays = ['日', '一', '二', '三', '四', '五', '六']

// 表单
const form = ref({
  prompt: '',
  freq: 'daily',
  time: null,
  weekdays: [],
  monthDay: 1,
  onceDate: null,
})

// 计算属性
const pendingCount = computed(() => tasks.value.filter(t => t.status === 'pending').length)
const runningCount = computed(() => tasks.value.filter(t => t.status === 'running').length)
const doneCount = computed(() => tasks.value.filter(t => t.status === 'done' || t.status === 'completed').length)
const failedCount = computed(() => tasks.value.filter(t => t.status === 'failed').length)

const filteredTasks = computed(() => {
  if (statusFilter.value === 'all') return tasks.value
  return tasks.value.filter(t => t.status === statusFilter.value)
})

// AI cron 生成
const cronPreview = computed(() => {
  const f = form.value
  if (!f.time || !f.prompt) return ''
  const [h, m] = f.time.split(':')
  switch (f.freq) {
    case 'once': return `${m} ${h} ${f.onceDate ? new Date(f.onceDate).getDate() : '*'} ${f.onceDate ? new Date(f.onceDate).getMonth() + 1 : '*'} *`
    case 'daily': return `${m} ${h} * * *`
    case 'weekdays': return `${m} ${h} * * 1-5`
    case 'weekly': return `${m} ${h} * * ${f.weekdays.sort().join(',') || '*'}`
    case 'monthly': return `${m} ${h} ${f.monthDay} * *`
    default: return ''
  }
})

function disabledHours() {
  const now = new Date()
  const h = []
  if (form.value.freq === 'once' && form.value.onceDate) {
    const d = new Date(form.value.onceDate)
    if (d.toDateString() === now.toDateString()) {
      for (let i = 0; i < now.getHours(); i++) h.push(i)
    }
  }
  return h
}

function disabledDate(time) {
  return time.getTime() < Date.now() - 86400000
}

function toggleDay(i) {
  const idx = form.value.weekdays.indexOf(i)
  if (idx >= 0) form.value.weekdays.splice(idx, 1)
  else form.value.weekdays.push(i)
}

// 格式化
function formatTime(task) {
  const parts = (task.cron || '').split(' ')
  if (parts.length === 5) return `${parts[1].padStart(2, '0')}:${parts[0].padStart(2, '0')}`
  return '--:--'
}

function formatDate(ts) {
  if (!ts) return ''
  return new Date(ts).toLocaleDateString('zh-CN')
}

function relativeTime(ts) {
  if (!ts) return ''
  const diff = Date.now() - (typeof ts === 'number' ? ts : new Date(ts).getTime())
  if (diff < 60000) return '刚刚'
  if (diff < 3600000) return `${Math.floor(diff / 60000)} 分钟前`
  if (diff < 86400000) return `${Math.floor(diff / 3600000)} 小时前`
  return `${Math.floor(diff / 86400000)} 天前`
}

function statusTag(status) {
  return { pending: 'info', running: 'warning', done: 'success', completed: 'success', failed: 'danger' }[status] || 'info'
}

function statusLabel(status) {
  return { pending: '待执行', running: '运行中', done: '已完成', completed: '已完成', failed: '失败' }[status] || status
}

// API
async function fetchTasks() {
  loading.value = true
  try {
    const { data } = await axios.get('/api/cron')
    tasks.value = (data.tasks || []).map(t => ({ ...t, status: t.status || 'pending' }))
  } catch { tasks.value = [] }
  finally { loading.value = false }
}

async function submitTask() {
  if (!form.value.prompt || !form.value.time) return
  saving.value = true
  try {
    const payload = {
      cron: cronPreview.value,
      prompt: form.value.prompt,
      recurring: form.value.freq !== 'once',
    }
    await axios.post('/api/cron', payload)
    showCreate.value = false
    form.value = { prompt: '', freq: 'daily', time: null, weekdays: [], monthDay: 1, onceDate: null }
    await fetchTasks()
  } catch { /* ignore */ }
  finally { saving.value = false }
}

async function runTask(task) {
  runningId.value = task.id
  try { await axios.post(`/api/tasks/run`, { prompt: task.prompt }) }
  catch { /* ignore */ }
  finally { runningId.value = null }
}

async function deleteTask(id) {
  try {
    await axios.delete(`/api/cron/${id}`)
    await fetchTasks()
  } catch { /* ignore */ }
}

// 初始化
fetchTasks()
</script>

<style scoped>
.scheduler-page { padding: 4px 4px 24px; }

/* ===== 页头（与知识库页同款） ===== */
.kb-top { display: flex; align-items: flex-start; justify-content: space-between; margin-bottom: 18px; }
.kb-title { font-size: 26px; font-weight: 700; letter-spacing: -0.02em; margin: 0; font-family: var(--font-display); }
.kb-desc { font-size: 12px; color: var(--text-tertiary); margin: 6px 0 0; max-width: 560px; }

/* ===== 任务总览 banner ===== */
.all-tasks {
  position: relative; overflow: hidden;
  border-radius: var(--radius-xl); padding: 20px 26px;
  background: linear-gradient(115deg, var(--tz-purple-soft), var(--tz-blue-soft));
  border: 1px solid var(--border-light);
  display: flex; align-items: center; justify-content: space-between;
  margin-bottom: 26px;
}
.all-tasks-title { font-size: 16px; font-weight: 700; color: var(--text-primary); }
.all-tasks-desc { font-size: 12px; color: var(--text-secondary); margin-top: 6px; max-width: 520px; }
.all-tasks-meta { font-size: 11px; color: var(--text-tertiary); margin-top: 10px; }
.all-tasks-icons { position: relative; width: 340px; height: 84px; flex-shrink: 0; }
.ft-clock, .ft-alarm, .ft-repeat, .ft-cal {
  position: absolute; width: 40px; height: 40px; border-radius: 10px;
  display: grid; place-items: center; font-size: 17px;
  box-shadow: var(--shadow-soft);
}
.ft-clock  { background: var(--tz-purple-soft); color: var(--tz-purple-ink); top: 8px;  left: 10px;  transform: rotate(-6deg); }
.ft-alarm  { background: var(--tz-yellow-soft); color: var(--tz-yellow-ink); top: 36px; left: 84px;  transform: rotate(5deg); }
.ft-repeat { background: var(--tz-green-soft);  color: var(--tz-green-ink);  top: 6px;  left: 170px; transform: rotate(4deg); }
.ft-cal    { background: var(--tz-blue-soft);   color: var(--tz-blue-ink);   top: 38px; left: 246px; transform: rotate(-5deg); }

/* ===== 任务列表 ===== */
.topic-bar { display: flex; align-items: center; gap: 10px; margin-bottom: 16px; }
.topic-label { font-size: 14px; font-weight: 700; margin-right: auto; }

/* 状态筛选：胶囊式分段控件 */
.status-tabs :deep(.el-radio-button__inner) {
  --el-radio-button-checked-bg-color: var(--accent);
  --el-radio-button-checked-border-color: var(--accent);
  --el-radio-button-checked-text-color: var(--text-on-accent);
  --el-radio-button-checked-hover-bg-color: var(--accent-hover);
  --el-radio-button-checked-hover-border-color: var(--accent-hover);
  --el-radio-button-checked-hover-text-color: var(--text-on-accent);
  background: var(--bg-card);
  border: 1px solid var(--border-input);
  color: var(--text-secondary);
}
.status-tabs :deep(.el-radio-button__inner:hover) { color: var(--text-primary); border-color: var(--accent); }
.status-tabs :deep(.el-radio-button:not(:first-child) .el-radio-button__inner) { border-left: none; }
.status-tabs :deep(.el-radio-button:first-child .el-radio-button__inner) { border-radius: 999px 0 0 999px; }
.status-tabs :deep(.el-radio-button:last-child .el-radio-button__inner) { border-radius: 0 999px 999px 0; }
.status-tabs :deep(.el-radio-button.is-active .el-radio-button__inner) { box-shadow: none; }

/* ===== 任务卡片网格 ===== */
.task-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(320px, 1fr)); gap: 16px; }
.task-card {
  position: relative; overflow: hidden;
  display: flex; flex-direction: column; gap: 10px;
  background: var(--bg-card); border: 1px solid var(--border-light);
  border-radius: var(--radius-lg); padding: 16px 16px 12px;
  box-shadow: var(--shadow-soft);
  transition: all .2s;
}
.task-card:hover { box-shadow: var(--shadow); transform: translateY(-2px); }

/* 顶部状态色条 */
.task-card::before {
  content: ''; position: absolute; top: 0; left: 0; right: 0; height: 3px;
}
.task-card.st-pending::before { background: var(--text-muted); }
.task-card.st-running::before { background: var(--tz-yellow-ink); }
.task-card.st-done::before, .task-card.st-completed::before { background: var(--success); }
.task-card.st-failed::before { background: var(--danger); }

.task-card-top { display: flex; align-items: center; justify-content: space-between; gap: 8px; }
.cron-chip {
  font-family: 'SFMono-Regular', Consolas, 'Liberation Mono', monospace;
  font-size: 11px; letter-spacing: 0.02em;
  color: var(--text-secondary);
  background: var(--bg-subtle);
  border: 1px solid var(--border-light);
  border-radius: 999px;
  padding: 3px 10px;
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
  max-width: 70%;
}
.task-time { display: flex; align-items: baseline; gap: 8px; }
.time-value { font-size: 26px; font-weight: 700; color: var(--text-primary); font-family: var(--font-display); letter-spacing: -0.02em; }
.time-label { font-size: 11px; color: var(--text-tertiary); }

.task-prompt {
  font-size: 13px; line-height: 1.6; color: var(--text-secondary);
  display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical;
  overflow: hidden; min-height: 41px;
}

.task-meta { display: flex; gap: 12px; flex-wrap: wrap; font-size: 11px; color: var(--text-tertiary); }
.meta-item { display: inline-flex; align-items: center; gap: 3px; }

.task-actions {
  display: flex; align-items: center; justify-content: space-between;
  border-top: 1px solid var(--border-light);
  padding-top: 10px; margin-top: 2px;
}
.run-btn { font-size: 12px; padding: 6px 14px; }
.del-btn { padding: 0 6px; }

/* ===== 空状态：emoji + 文案 + CTA ===== */
.task-empty { text-align: center; padding: 56px 0 48px; color: var(--text-tertiary); }
.task-empty-emoji { font-size: 44px; margin-bottom: 12px; }
.task-empty-text { font-size: 13px; color: var(--text-secondary); margin-bottom: 18px; }

/* ===== 新建弹窗内的频次选择（保持不变） ===== */
.freq-tabs { width: 100%; }
.weekday-pills { display: flex; gap: 4px; }
.day-pill {
  width: 32px; height: 32px; border-radius: 50%;
  display: flex; align-items: center; justify-content: center;
  font-size: 12px; cursor: pointer; border: 1px solid var(--border);
  transition: all 0.15s; user-select: none;
}
.day-pill:hover { border-color: var(--primary); }
.day-pill.active { background: var(--primary); color: var(--text-on-accent); border-color: var(--primary); }
</style>
