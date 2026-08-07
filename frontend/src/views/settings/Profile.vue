<template>
  <el-row :gutter="20">
    <!-- 用户信息卡片 -->
    <el-col :span="8">
      <el-card>
        <div style="text-align:center;padding:20px 0">
          <el-avatar :size="80" :src="profile.avatar || undefined" style="background:#409EFF">
            {{ profile.username?.charAt(0)?.toUpperCase() || '?' }}
          </el-avatar>
          <h2 style="margin:12px 0 4px">{{ profile.username || '未登录' }}</h2>
          <div style="color:#999;font-size:13px">{{ profile.email || '未绑定邮箱' }}</div>
          <div style="margin-top:8px;font-size:12px;color:#bbb">注册于 {{ profile.created_at || '未知' }}</div>
        </div>
      </el-card>
    </el-col>

    <!-- 统计信息 -->
    <el-col :span="16">
      <el-card>
        <template #header><span><el-icon><DataAnalysis /></el-icon> 使用统计</span></template>
        <el-row :gutter="20">
          <el-col :span="8" v-for="stat in stats" :key="stat.label">
            <el-card shadow="never" style="text-align:center;margin-bottom:12px">
              <div style="font-size:28px;font-weight:bold;color:#409EFF">{{ stat.value }}</div>
              <div style="font-size:13px;color:#666;margin-top:4px">{{ stat.label }}</div>
            </el-card>
          </el-col>
        </el-row>
      </el-card>

      <el-card style="margin-top:16px">
        <template #header><span><el-icon><Setting /></el-icon> 账户设置</span></template>
        <el-form label-width="100px">
          <el-form-item label="用户名">
            <el-input v-model="profile.username" disabled />
          </el-form-item>
          <el-form-item label="邮箱">
            <el-input v-model="profile.email" placeholder="绑定邮箱用于密码找回" />
          </el-form-item>
          <el-form-item>
            <el-button type="primary" @click="saveProfile">保存</el-button>
          </el-form-item>
        </el-form>
      </el-card>
    </el-col>
  </el-row>
</template>

<script setup>
import { ref, reactive } from 'vue'
import { ElMessage } from 'element-plus'
import request from '../../utils/request'

const profile = ref({ username: '', email: '', avatar: '', created_at: '' })
const stats = ref([])

const loadProfile = async () => {
  try {
    const res = await request.get('/api/auth/me')
    profile.value = res
    if (res.stats) {
      stats.value = [
        { label: '总对话数', value: res.stats.sessions || 0 },
        { label: '今日消息', value: res.stats.messages_today || 0 },
        { label: '总消息数', value: res.stats.total_messages || 0 },
      ]
    }
  } catch {
    ElMessage.warning('请先登录')
  }
}

const saveProfile = async () => {
  ElMessage.success('保存成功（本地）')
}

loadProfile()
</script>
