<template>
  <div class="market-page">
    <!-- 搜索 -->
    <el-input v-model="query" placeholder="搜索..." size="small" clearable style="max-width:280px;margin-bottom:12px" />

    <!-- 列表 -->
    <div class="market-grid">
      <div v-for="item in filtered" :key="item.id" class="market-card">
        <div class="mc-icon">{{ iconMap[item.category] || '📦' }}</div>
        <div class="mc-body">
          <div class="mc-name">{{ item.title || item.name || item.id }}</div>
          <div class="mc-desc">{{ (item.description || '').slice(0, 60) }}</div>
          <div class="mc-tags">
            <el-tag v-for="t in (item.tags||[]).slice(0,2)" :key="t" size="small" round>{{ t }}</el-tag>
          </div>
        </div>
        <div class="mc-actions">
          <template v-if="item.installable !== false">
            <el-button v-if="item.installed" size="small" type="danger" plain round @click="uninstall(item)">卸载</el-button>
            <el-button v-else size="small" type="primary" round @click="install(item)">安装</el-button>
          </template>
          <el-button size="small" round @click="openEdit(item)">修改</el-button>
          <el-button v-if="item.deletable" size="small" text type="danger" @click="remove(item)">删除</el-button>
        </div>
      </div>
    </div>
    <el-empty v-if="filtered.length === 0" :image-size="60" description="暂无数据" />

  </div>
</template>

<script>
import axios from 'axios'
import { ElMessage, ElMessageBox } from 'element-plus'

const APIS = {
  tools: { list: '/api/tool-marketplace', install: '/api/tool-marketplace', installedField: 'installed', deleteBase: '/api/upload/tools' },
  mcp: { list: '/api/mcp/marketplace', install: '/api/mcp', installedField: 'installed', deleteBase: '/api/upload/mcp' },
  skills: { list: '/api/skills/marketplace', install: '/api/skills', installedField: 'installed', deleteBase: '/api/upload/skills' },
}

export default {
  props: { title: String, api: String, type: String },
  emits: ['request-upload'],
  data() {
    return {
      items: [], query: '',
      form: { name: '', desc: '' },
      iconMap: { builtin: '🔧', mcp: '🔗', skill: '🧩', tool: '🛠' },
    }
  },
  computed: {
    filtered() {
      const q = this.query.toLowerCase()
      return q ? this.items.filter(i => (i.title||i.name||i.id).toLowerCase().includes(q)) : this.items
    },
    cfg() { return APIS[this.type] || APIS.tools },
  },
  methods: {
    async fetch() {
      try {
        const r = await axios.get(this.api)
        this.items = r.data?.items || r.data || []
      } catch {}
    },
    async install(item) {
      const api = this.cfg.install
      const id = item.id || item.name
      try {
        const url = api.includes('/marketplace') ? `${api}/../install` : `${api}/install`
        await axios.post(`${api}/${id}/install`, { id })
        item[this.cfg.installedField] = true
        ElMessage.success('安装成功')
      } catch (e) {
        // 尝试备用路径
        try {
          await axios.post(`${api}/install`, { id })
          item[this.cfg.installedField] = true
          ElMessage.success('安装成功')
        } catch {
          ElMessage.error('安装失败')
        }
      }
    },
    async uninstall(item) {
      const api = this.cfg.install
      const id = item.id || item.name
      try {
        await axios.post(`${api}/${id}/uninstall`, { id })
        item[this.cfg.installedField] = false
        ElMessage.success('卸载成功')
      } catch {
        try {
          await axios.post(`${api}/uninstall`, { id })
          item[this.cfg.installedField] = false
          ElMessage.success('卸载成功')
        } catch {
          ElMessage.error('卸载失败')
        }
      }
    },
    openEdit(item) {
      // 修改 = 重新上传同名资源覆盖(真实替换)
      this.$emit('request-upload', item.name || item.id)
    },
    async remove(item) {
      const label = item.title || item.name || item.id
      const name = item.name || item.id
      try {
        await ElMessageBox.confirm(`确认删除「${label}」？删除后需重新上传。`, '删除', { type: 'warning' })
      } catch { return }
      try {
        await axios.delete(`${this.cfg.deleteBase}/${name}`)
        this.items = this.items.filter(i => i.id !== item.id)
        ElMessage.success('已删除')
      } catch (e) {
        ElMessage.error('删除失败: ' + (e.response?.data?.detail || e.message))
      }
    },
    addItem() {
      if (!this.form.name) return
      this.items.unshift({
        id: Date.now().toString(),
        name: this.form.name,
        title: this.form.name,
        description: this.form.desc,
        installed: false,
        category: this.type === 'tools' ? 'builtin' : this.type,
        tags: [],
      })
      this.showAdd = false
      this.form = { name: '', desc: '' }
      ElMessage.success('添加成功')
    },
  },
  mounted() { this.fetch() },
}
</script>

<style scoped>
.market-page { }
.market-top { display: flex; align-items: center; justify-content: space-between; margin-bottom: 12px; }
.market-title { font-size: 18px; font-weight: 700; margin: 0; }
.market-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(320px, 1fr)); gap: 8px; }
.market-card {
  display: flex; align-items: center; gap: 10px;
  padding: 12px; border: 1px solid var(--border); border-radius: 10px;
  background: var(--bg-card); transition: all .15s;
}
.market-card:hover { box-shadow: var(--shadow-sm); }
.mc-icon { font-size: 20px; width: 36px; height: 36px; display: grid; place-items: center; background: var(--bg-subtle); border-radius: 8px; flex-shrink: 0; }
.mc-body { flex: 1; min-width: 0; }
.mc-name { font-size: 13px; font-weight: 500; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.mc-desc { font-size: 11px; color: var(--text-tertiary); margin-top: 2px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.mc-tags { margin-top: 4px; display: flex; gap: 4px; }
.mc-actions { display: flex; align-items: center; gap: 4px; flex-shrink: 0; }
</style>
