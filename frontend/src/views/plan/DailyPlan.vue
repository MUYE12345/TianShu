<template>
  <div class="scheduler-page">
    <!-- 顶部 -->
    <div class="scheduler-header">
      <div>
        <h1 class="page-title">定时任务</h1>
        <p class="page-desc">创建定时任务，到时间自动执行</p>
      </div>
      <el-button type="primary" size="large" round @click="showCreate = true">
        <el-icon><Plus /></el-icon> 新建任务
      </el-button>
    </div>

    <!-- 任务列表 -->
    <div class="task-board" v-loading="loading">
      <!-- 状态分组 -->
      <div class="status-tabs">
        <el-radio-group v-model="statusFilter" size="small">
          <el-radio-button value="all">全部 ({{ tasks.length }})</el-radio-button>
          <el-radio-button value="pending">待执行 ({{ pendingCount }})</el-radio-button>
          <el-radio-button value="running">运行中 ({{ runningCount }})</el-radio-button>
          <el-radio-button value="done">已完成 ({{ doneCount }})</el-radio-button>
          <el-radio-button value="failed">失败 ({{ failedCount }})</el-radio-button>
        </el-radio-group>
      </div>

      <!-- 空状态 -->
      <el-empty v-if="!loading && filteredTasks.length === 0" :image-size="80" class="empty-box">
        <template #description>暂无定时任务，点击右上角新建</template>
      </el-empty>

      <!-- 任务卡片 -->
      <div v-for="task in filteredTasks" :key="task.id" class="task-card">
        <div class="task-left">
          <div class="task-time">
            <span class="time-value">{{ formatTime(task) }}</span>
            <span class="time-label">{{ task.label || '' }}</span>
          </div>
        </div>
        <div class="task-divider" :class="task.status" />
        <div class="task-body">
          <div class="task-title">{{ task.prompt }}</div>
          <div class="task-meta">
            <el-tag :type="statusTag(task.status)" size="small" effect="plain" round>
              {{ statusLabel(task.status) }}
            </el-tag>
            <span class="meta-time">创建于 {{ formatDate(task.createdAt) }}</span>
            <span v-if="task.lastFiredAt" class="meta-time">上次运行 {{ relativeTime(task.lastFiredAt) }}</span>
          </div>
        </div>
        <div class="task-actions">
          <el-button text size="small" type="primary" @click="runTask(task)">▶ 运行</el-button>
          <el-popconfirm title="确认删除？" @confirm="deleteTask(task.id)">
            <template #reference>
              <el-button text size="small" type="danger">✕</el-button>
            </template>
          </el-popconfirm>
        </div>
      </div>
    </div>

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
.scheduler-page { padding: 20px; height: 100%; display: flex; flex-direction: column; }
.scheduler-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px; }
.page-title { margin: 0; font-size: 20px; font-weight: 700; }
.page-desc { margin: 4px 0 0; font-size: 13px; color: var(--text-tertiary); }

.task-board { flex: 1; overflow-y: auto; }
.status-tabs { margin-bottom: 16px; }

.empty-box { margin-top: 60px; }

/* 任务卡片 */
.task-card {
  display: flex; align-items: stretch; gap: 0;
  background: var(--bg-card); border: 1px solid var(--border);
  border-radius: 12px; margin-bottom: 10px; overflow: hidden;
  transition: all 0.15s;
}
.task-card:hover { box-shadow: 0 2px 8px rgba(0,0,0,0.06); }

.task-left {
  display: flex; flex-direction: column; align-items: center;
  justify-content: center; min-width: 100px; padding: 16px;
}
.time-value { font-size: 22px; font-weight: 700; color: var(--text-primary); }
.time-label { font-size: 11px; color: var(--text-tertiary); margin-top: 2px; }

.task-divider { width: 3px; flex-shrink: 0; }
.task-divider.pending { background: #d1d5db; }
.task-divider.running { background: #f59e0b; }
.task-divider.done, .task-divider.completed { background: #22c55e; }
.task-divider.failed { background: #ef4444; }

.task-body { flex: 1; padding: 14px 16px; min-width: 0; }
.task-title { font-size: 14px; line-height: 1.5; margin-bottom: 8px; }
.task-meta { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.meta-time { font-size: 11px; color: var(--text-tertiary); }

.task-actions { display: flex; flex-direction: column; justify-content: center; gap: 4px; padding: 8px 12px; border-left: 1px solid var(--border); }

/* 频次选择 */
.freq-tabs { width: 100%; }

/* 星期选择 - 小圆片 */
.weekday-pills { display: flex; gap: 4px; }
.day-pill {
  width: 32px; height: 32px; border-radius: 50%;
  display: flex; align-items: center; justify-content: center;
  font-size: 12px; cursor: pointer; border: 1px solid var(--border);
  transition: all 0.15s; user-select: none;
}
.day-pill:hover { border-color: var(--primary); }
.day-pill.active { background: var(--primary); color: #fff; border-color: var(--primary); }
</style>
