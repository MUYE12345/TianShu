<template>
  <el-card>
    <template #header>
      <div style="display:flex;justify-content:space-between;align-items:center">
        <span><el-icon><List /></el-icon> 运行日志</span>
        <div>
          <el-input v-model="keyword" placeholder="过滤关键词" size="small" style="width:200px;margin-right:8px" clearable @keyup.enter="loadLogs" />
          <el-button size="small" @click="loadLogs" :loading="loading"><el-icon><Refresh /></el-icon> 刷新</el-button>
        </div>
      </div>
    </template>

    <div v-loading="loading">
      <div style="font-size:12px;color:#999;margin-bottom:8px">
        来源: {{ source }} | 共 {{ totalLines }} 行 | 显示最近 {{ limit }} 行
      </div>
      <div ref="logContainer" style="background:#1e1e1e;color:#d4d4d4;padding:12px;border-radius:6px;font-family:'Consolas','Courier New',monospace;font-size:12px;line-height:1.6;max-height:600px;overflow-y:auto;white-space:pre-wrap">
        <div v-for="(line, idx) in logLines" :key="idx" style="display:flex">
          <span style="color:#858585;min-width:40px;text-align:right;margin-right:12px;user-select:none">{{ totalLines - logLines.length + idx + 1 }}</span>
          <span :style="logColor(line)">{{ line }}</span>
        </div>
        <div v-if="logLines.length === 0" style="color:#666;text-align:center;padding:40px">暂无日志</div>
      </div>
    </div>
  </el-card>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import request from '../../utils/request'

const logLines = ref([])
const source = ref('')
const totalLines = ref(0)
const loading = ref(false)
const keyword = ref('')
const limit = ref(100)
const logContainer = ref(null)

const loadLogs = async () => {
  loading.value = true
  try {
    const res = await request.get('/api/logs/tail', {
      params: { lines: limit.value, keyword: keyword.value },
    })
    logLines.value = res.lines || []
    source.value = res.source || 'none'
    totalLines.value = res.total || 0
    // 自动滚动到底部
    setTimeout(() => {
      if (logContainer.value) {
        logContainer.value.scrollTop = logContainer.value.scrollHeight
      }
    }, 50)
  } catch {
    logLines.value = ['[无法加载日志]']
  }
  loading.value = false
}

const logColor = (line) => {
  if (line.includes('ERROR') || line.includes('Error')) return { color: '#f44747' }
  if (line.includes('WARNING') || line.includes('warning')) return { color: '#dcdcaa' }
  if (line.includes('INFO')) return { color: '#6a9955' }
  return {}
}

onMounted(loadLogs)
</script>
