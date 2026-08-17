<template>
  <div>
    <el-card style="margin-bottom:12px">
      <template #header><span><el-icon><Lock /></el-icon> 安全围栏（Tool Harness）</span></template>
      <el-descriptions :column="3" border size="small">
        <el-descriptions-item label="安全模式">
          <el-switch v-model="st.safe_mode" @change="setSafeMode" />
          <div class="hint">危险工具（shell/cli/git/沙箱代码执行/用户上传工具）将被禁止</div>
        </el-descriptions-item>
        <el-descriptions-item label="紧急熔断">
          <el-switch v-model="st.emergency_stop" @change="setEmergencyStop" />
          <div class="hint">开启后暂停全部工具执行（事故时先按这个）</div>
        </el-descriptions-item>
        <el-descriptions-item label="路径围栏">
          <el-switch v-model="st.path_fence" @change="setPathFence" />
          <div class="hint">写文件/工作目录限制在项目根内</div>
        </el-descriptions-item>
        <el-descriptions-item label="Docker 沙箱">
          <el-tag :type="st.docker_available ? 'success' : 'danger'" size="small">
            {{ st.docker_available ? '可用' : '不可用' }}
          </el-tag>
          <div class="hint">代码/命令执行必须经 Docker（无本地直跑）</div>
        </el-descriptions-item>
        <el-descriptions-item label="每分钟限流">
          <span>{{ st.max_calls_per_minute }} 次</span>
        </el-descriptions-item>
        <el-descriptions-item label="今日统计">
          <span>检查 {{ st.stats?.checked }} / 执行 {{ st.stats?.executed }} / 拦截 {{ st.stats?.blocked }}</span>
        </el-descriptions-item>
      </el-descriptions>
    </el-card>

    <el-card style="margin-bottom:12px">
      <template #header><span><el-icon><Tools /></el-icon> 禁用工具名单</span></template>
      <div style="display:flex;gap:8px;margin-bottom:10px">
        <el-input v-model="blockInput" placeholder="工具名，如 shell_execute" style="width:240px" />
        <el-button type="danger" size="small" @click="addBlock">禁用</el-button>
      </div>
      <el-tag v-for="t in st.blocked_tools" :key="t" closable style="margin:0 6px 6px 0"
              type="warning" @close="unblock(t)">{{ t }}</el-tag>
      <el-empty v-if="!st.blocked_tools?.length" description="未禁用任何工具" :image-size="50" />
    </el-card>

    <el-card style="margin-bottom:12px">
      <template #header><span><el-icon><DataAnalysis /></el-icon> 工具风险分级</span></template>
      <el-table :data="riskRows" size="small" stripe max-height="260">
        <el-table-column prop="name" label="工具" width="200" />
        <el-table-column prop="risk" label="风险" width="100">
          <template #default="{row}">
            <el-tag :type="row.risk==='dangerous'?'danger':row.risk==='medium'?'warning':'success'" size="small">
              {{ {safe:'安全',medium:'中等',dangerous:'危险'}[row.risk] }}
            </el-tag>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <el-card>
      <template #header>
        <div style="display:flex;justify-content:space-between">
          <span><el-icon><List /></el-icon> 最近调用审计（含被拦截记录）</span>
          <el-button size="small" @click="loadAll">刷新</el-button>
        </div>
      </template>
      <el-table :data="audit" size="small" stripe max-height="400">
        <el-table-column prop="ts" label="时间" width="170" />
        <el-table-column prop="tool" label="工具" width="150" />
        <el-table-column label="结果" width="80">
          <template #default="{row}">
            <el-tag :type="row.ok?'success':'danger'" size="small">{{ row.ok?'执行':'拦截' }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="reason" label="原因/结果" min-width="220" show-overflow-tooltip />
        <el-table-column prop="args" label="参数" min-width="200" show-overflow-tooltip />
      </el-table>
    </el-card>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import request from '../../utils/request'
import { ElMessage } from 'element-plus'
import { Lock, Tools, DataAnalysis, List } from '@element-plus/icons-vue'

const st = ref({ safe_mode: true, emergency_stop: false, path_fence: true,
                 docker_available: false, blocked_tools: [], max_calls_per_minute: 60,
                 stats: { checked: 0, executed: 0, blocked: 0 }, risk_table: {} })
const audit = ref([])
const blockInput = ref('')
const riskRows = computed(() =>
  Object.entries(st.value.risk_table || {}).map(([name, risk]) => ({ name, risk })))

async function loadAll() {
  try {
    const [s, a] = await Promise.all([
      request.get('/api/harness/status'),
      request.get('/api/harness/audit?n=50'),
    ])
    st.value = s.data
    audit.value = a.data?.items || []
  } catch (e) {
    ElMessage.error('加载安全围栏失败: ' + (e.response?.data?.detail || e.message))
  }
}
async function setSafeMode(v) { await request.post('/api/harness/safe-mode', { enabled: v }); ElMessage.success(v ? '安全模式已开启' : '安全模式已关闭') }
async function setEmergencyStop(v) { await request.post('/api/harness/emergency-stop', { enabled: v }); ElMessage.success(v ? '已紧急熔断' : '已解除熔断') }
async function setPathFence(v) { await request.post('/api/harness/path-fence', { enabled: v }); ElMessage.success(v ? '路径围栏已开启' : '路径围栏已关闭') }
async function addBlock() {
  const name = blockInput.value.trim()
  if (!name) return
  await request.post('/api/harness/block-tool', { name, blocked: true })
  blockInput.value = ''
  ElMessage.success(`已禁用工具: ${name}`)
  await loadAll()
}
async function unblock(name) {
  await request.post('/api/harness/block-tool', { name, blocked: false })
  ElMessage.success(`已放行工具: ${name}`)
  await loadAll()
}

onMounted(loadAll)
</script>

<style scoped>
.hint { font-size: 12px; color: #999; margin-top: 4px; line-height: 1.4; }
</style>
