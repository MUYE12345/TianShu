<template>
  <div class="market-wrapper">
    <!-- 顶栏: 标题 + 上传按钮 -->
    <div class="mw-header">
      <h1 class="mw-title">{{ config.title }}</h1>
      <el-button type="primary" size="small" round @click="showUpload = true">
        {{ config.uploadLabel }}
      </el-button>
    </div>

    <!-- 卡片列表 -->
    <MarketPage v-bind="config" :key="refreshKey" @request-upload="onRequestUpload" />

    <!-- ===== 上传弹窗 ===== -->
    <!-- 工具上传: .py / .zip -->
    <el-dialog v-model="showUpload" :title="config.uploadTitle" width="480px" v-if="config.type === 'tools'">
      <el-form label-position="top">
        <el-form-item label="工具包">
          <input type="file" accept=".py,.zip" @change="onFileChange" class="file-input" />
          <div class="file-hint">支持 .py 文件或 .zip 包（含 CLAUDE.md + 多个 .py）</div>
        </el-form-item>
        <el-form-item label="工具名称（可选）">
          <el-input v-model="toolName" placeholder="留空使用文件名" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showUpload = false">取消</el-button>
        <el-button type="primary" :loading="uploading" @click="uploadTool">上传</el-button>
      </template>
    </el-dialog>

    <!-- MCP 上传: 连接配置 -->
    <el-dialog v-model="showUpload" :title="config.uploadTitle" width="480px" v-if="config.type === 'mcp'">
      <el-form label-position="top">
        <el-form-item label="名称">
          <el-input v-model="mcpForm.name" placeholder="my-mcp-server" />
        </el-form-item>
        <el-form-item label="连接类型">
          <el-radio-group v-model="mcpForm.type">
            <el-radio value="stdio">stdio（命令）</el-radio>
            <el-radio value="http">HTTP</el-radio>
            <el-radio value="sse">SSE</el-radio>
          </el-radio-group>
        </el-form-item>
        <el-form-item v-if="mcpForm.type === 'stdio'" label="启动命令">
          <el-input v-model="mcpForm.command" placeholder="npx -y @modelcontextprotocol/server-filesystem" />
        </el-form-item>
        <el-form-item v-if="mcpForm.type === 'stdio'" label="参数">
          <el-input v-model="mcpForm.args" placeholder="参数，空格分隔" />
        </el-form-item>
        <el-form-item v-if="mcpForm.type !== 'stdio'" label="URL">
          <el-input v-model="mcpForm.url" placeholder="http://localhost:3000/mcp" />
        </el-form-item>
        <el-form-item label="环境变量（可选）">
          <el-input v-model="mcpForm.env" type="textarea" :rows="2" placeholder="KEY=VALUE 每行一个" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showUpload = false">取消</el-button>
        <el-button type="primary" :loading="uploading" @click="uploadMcp">注册</el-button>
      </template>
    </el-dialog>

    <!-- 技能上传: .md / .zip -->
    <el-dialog v-model="showUpload" :title="config.uploadTitle" width="480px" v-if="config.type === 'skills'">
      <el-form label-position="top">
        <el-form-item label="技能文件">
          <input type="file" accept=".md,.zip" @change="onFileChange" class="file-input" />
          <div class="file-hint">支持 SKILL.md / CLAUDE.md 或包含这些文件的 .zip 包</div>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showUpload = false">取消</el-button>
        <el-button type="primary" :loading="uploading" @click="uploadSkill">安装</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script>
import { ref, computed, reactive } from 'vue'
import { useRoute } from 'vue-router'
import axios from 'axios'
import { ElMessage } from 'element-plus'
import MarketPage from './MarketPage.vue'

const CONFIGS = {
  'tools': { type: 'tools', title: '🛠 工具市场', api: '/api/tool-marketplace', uploadLabel: '上传工具', uploadTitle: '上传工具' },
  'mcp-market': { type: 'mcp', title: '🔗 MCP 市场', api: '/api/mcp/marketplace', uploadLabel: '上传MCP', uploadTitle: '上传MCP' },
  'skills-market': { type: 'skills', title: '🧩 技能市场', api: '/api/skills/marketplace', uploadLabel: '上传技能', uploadTitle: '上传技能' },
}

export default {
  components: { MarketPage },
  setup() {
    const route = useRoute()
    const config = computed(() => CONFIGS[route.path.split('/').pop()] || CONFIGS.tools)
    const showUpload = ref(false)
    const uploading = ref(false)
    const refreshKey = ref(0)
    const selectedFile = ref(null)
    const toolName = ref('')
    const mcpForm = reactive({ name: '', type: 'stdio', command: '', args: '', url: '', env: '' })

    const onFileChange = (e) => { selectedFile.value = e.target.files[0] }

    const onRequestUpload = (name = '') => {
      // 重传/修改: 打开上传弹窗, 预填名称
      if (config.value.type === 'mcp') mcpForm.name = name || ''
      else toolName.value = name || ''
      showUpload.value = true
    }

    const uploadTool = async () => {
      if (!selectedFile.value) return
      uploading.value = true
      const fd = new FormData()
      fd.append('file', selectedFile.value)
      if (toolName.value) fd.append('name', toolName.value)
      try {
        await axios.post('/api/upload/tools', fd)
        ElMessage.success('工具上传成功')
        showUpload.value = false
        refreshKey.value++
      } catch (e) { ElMessage.error('上传失败: ' + (e.response?.data?.detail || e.message)) }
      finally { uploading.value = false }
    }

    const uploadMcp = async () => {
      if (!mcpForm.name) return
      uploading.value = true
      const body = { name: mcpForm.name, type: mcpForm.type }
      if (mcpForm.type === 'stdio') {
        body.command = mcpForm.command
        body.args = mcpForm.args ? mcpForm.args.split(/\s+/) : []
        if (mcpForm.env) {
          body.env = Object.fromEntries(mcpForm.env.split('\n').filter(Boolean).map(l => l.split('=', 2)))
        }
      } else {
        body.url = mcpForm.url
      }
      try {
        await axios.post('/api/upload/mcp', body)
        ElMessage.success('MCP 服务器已注册')
        showUpload.value = false
        refreshKey.value++
      } catch (e) { ElMessage.error('注册失败: ' + (e.response?.data?.detail || e.message)) }
      finally { uploading.value = false }
    }

    const uploadSkill = async () => {
      if (!selectedFile.value) return
      uploading.value = true
      const fd = new FormData()
      fd.append('file', selectedFile.value)
      try {
        await axios.post('/api/upload/skills', fd)
        ElMessage.success('技能安装成功')
        showUpload.value = false
        refreshKey.value++
      } catch (e) { ElMessage.error('安装失败: ' + (e.response?.data?.detail || e.message)) }
      finally { uploading.value = false }
    }

    return { config, showUpload, uploading, refreshKey, selectedFile, toolName, mcpForm, onFileChange, onRequestUpload, uploadTool, uploadMcp, uploadSkill }
  }
}
</script>

<style scoped>
.mw-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 16px; }
.mw-title { font-size: 18px; font-weight: 700; margin: 0; }
.file-input { width: 100%; padding: 8px; border: 1px solid var(--border); border-radius: 6px; }
.file-hint { font-size: 12px; color: var(--text-tertiary); margin-top: 4px; }
</style>
