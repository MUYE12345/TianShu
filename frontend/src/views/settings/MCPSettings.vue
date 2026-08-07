<template>
  <el-card>
    <template #header>
      <div style="display:flex;justify-content:space-between">
        <span><el-icon><Connection /></el-icon> MCP工具管理</span>
        <el-button size="small" type="primary" @click="showInstall=true">+ 安装</el-button>
      </div>
    </template>

    <el-table :data="tools" stripe>
      <el-table-column prop="name" label="工具名" width="120" />
      <el-table-column prop="description" label="描述" min-width="200" />
      <el-table-column prop="category" label="类型" width="80" />
      <el-table-column label="状态" width="80">
        <template #default="{row}">
          <el-tag :type="row.enabled?'success':'info'" size="small">{{ row.enabled?'已启用':'已禁用' }}</el-tag>
        </template>
      </el-table-column>
    </el-table>

    <el-dialog v-model="showInstall" title="安装MCP工具" width="500px">
      <el-form label-width="100px">
        <el-form-item label="工具名"><el-input v-model="installForm.name" /></el-form-item>
        <el-form-item label="命令"><el-input v-model="installForm.command" placeholder="如: npx" /></el-form-item>
        <el-form-item label="参数"><el-input v-model="installForm.args" placeholder="如: -y @modelcontextprotocol/server-filesystem /tmp" /></el-form-item>
        <el-form-item label="环境变量"><el-input v-model="installForm.env" type="textarea" :rows="3" placeholder="KEY=VALUE&#10;每行一个" /></el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showInstall=false">取消</el-button>
        <el-button type="primary" @click="doInstall">安装</el-button>
      </template>
    </el-dialog>
  </el-card>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import request from '../../utils/request'
import { ElMessage } from 'element-plus'

const tools = ref([])
const showInstall = ref(false)
const installForm = ref({ name: '', command: '', args: '', env: '' })

onMounted(async () => {
  try {
    const res = await request.get('/api/mcp')
    tools.value = res || []
  } catch {}
})

const doInstall = async () => {
  try {
    await request.post('/api/mcp/install', installForm.value)
    ElMessage.success('安装成功')
    showInstall.value = false
  } catch { ElMessage.error('安装失败') }
}
</script>
