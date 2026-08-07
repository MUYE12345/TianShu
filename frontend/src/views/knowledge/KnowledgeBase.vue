<template>
  <el-row :gutter="16">
    <el-col :span="8">
      <el-card>
        <template #header><span><el-icon><Folder /></el-icon> 知识库管理</span></template>
        <el-upload :action="uploadUrl" :on-success="onUpload" :on-error="onUploadError" multiple drag>
          <el-icon size="40"><UploadFilled /></el-icon>
          <div style="margin-top:8px">上传文档(TXT/PDF/MD)</div>
          <template #tip><div style="font-size:12px;color:#999">文件将自动解析并加入知识库</div></template>
        </el-upload>
        <el-divider />
        <h4>已上传文档</h4>
        <div v-for="doc in documents" :key="doc.id" style="padding:8px;border-bottom:1px solid #f0f0f0;font-size:13px">
          <el-icon><Document /></el-icon> {{ doc.filename || '文档' }}
          <el-tag size="small" :type="doc.status==='parsed'?'success':'warning'" style="float:right">{{ doc.status }}</el-tag>
        </div>
        <el-empty v-if="documents.length===0" description="还未上传知识文档" />
      </el-card>
    </el-col>
    <el-col :span="16">
      <el-card>
        <template #header><span><el-icon><Search /></el-icon> 知识检索</span></template>
        <el-input v-model="searchQuery" placeholder="搜索知识库..." @keyup.enter="searchKB">
          <template #append><el-button @click="searchKB" :loading="searching">搜索</el-button></template>
        </el-input>
        <div v-loading="searching" style="min-height:100px">
          <div v-for="(r, idx) in searchResults" :key="idx" style="padding:12px;border-bottom:1px solid #f0f0f0">
            <p style="font-size:13px;color:#333;white-space:pre-wrap">{{ r.content || r.body || '' }}</p>
            <div style="margin-top:4px;font-size:12px;color:#999">
              <el-tag size="small">{{ r.source || r.type || '知识' }}</el-tag>
              <span v-if="r.score"> 匹配度: {{ (r.score * 100).toFixed(0) }}%</span>
            </div>
          </div>
          <el-empty v-if="!searching && searchResults.length === 0 && searchQuery" description="未找到相关内容" />
          <el-empty v-if="!searching && searchResults.length === 0 && !searchQuery" description="输入关键词搜索知识库" />
        </div>
      </el-card>
    </el-col>
  </el-row>
</template>

<script setup>
import { ref, computed } from 'vue'
import request from '../../utils/request'
import { ElMessage } from 'element-plus'

const documents = ref([])
const searchQuery = ref('')
const searchResults = ref([])
const searching = ref(false)

const uploadUrl = computed(() => {
  const base = import.meta.env.BASE_URL || ''
  return `${base}api/storage/upload`
})

const onUpload = (res) => {
  documents.value.unshift(res)
  ElMessage.success('上传成功')
}

const onUploadError = () => {
  ElMessage.error('上传失败，请检查文件大小或格式')
}

const searchKB = async () => {
  if (!searchQuery.value) return
  searching.value = true
  searchResults.value = []
  try {
    const res = await request.get('/api/memory/search', { params: { q: searchQuery.value, limit: 10 } })
    // API返回格式兼容：可能是 {results: [...]} 或直接数组
    const data = res?.results || res || []
    searchResults.value = Array.isArray(data) ? data : [data]
  } catch {
    ElMessage.error('搜索失败')
  }
  searching.value = false
}
</script>
