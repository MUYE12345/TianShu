<template>
  <div class="login-page">
    <el-card style="width:420px;border-radius:12px">
      <template #header>
        <div style="text-align:center">
          <div class="login-logo">✦</div>
          <h2 style="margin:10px 0 0;font-size:22px;font-weight:700;letter-spacing:.08em">天枢</h2>
          <p style="color:#999;font-size:13px;margin:4px 0 0">Tianshu · 智能体中枢平台</p>
        </div>
      </template>

      <el-form :model="form" :rules="rules" ref="formRef" label-width="0" status-icon>
        <el-form-item prop="username">
          <el-input v-model="form.username" placeholder="用户名" :prefix-icon="User" size="large" />
        </el-form-item>
        <el-form-item prop="password">
          <el-input v-model="form.password" type="password" placeholder="密码" :prefix-icon="Lock" size="large" show-password @keyup.enter="handleLogin" />
        </el-form-item>
        <el-form-item>
          <el-button type="primary" @click="handleLogin" :loading="loading" style="width:100%" size="large">
            {{ loading ? '登录中...' : '登录' }}
          </el-button>
        </el-form-item>
        <el-form-item>
          <el-button @click="handleRegister" :loading="regLoading" style="width:100%" size="large">
            {{ regLoading ? '注册中...' : '注册账号' }}
          </el-button>
        </el-form-item>
        <el-form-item v-if="errorMsg">
          <el-alert :title="errorMsg" type="error" show-icon :closable="true" @close="errorMsg=''" />
        </el-form-item>
      </el-form>
    </el-card>
  </div>
</template>

<script setup>
import { reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { User, Lock } from '@element-plus/icons-vue'
import request from '../utils/request'
import { ElMessage } from 'element-plus'

const router = useRouter()
const formRef = ref(null)
const loading = ref(false)
const regLoading = ref(false)
const errorMsg = ref('')

const form = reactive({ username: '', password: '' })
const rules = {
  username: [
    { required: true, message: '请输入用户名', trigger: 'blur' },
    { min: 2, max: 20, message: '长度2-20字符', trigger: 'blur' }
  ],
  password: [
    { required: true, message: '请输入密码', trigger: 'blur' },
    { min: 4, message: '至少4个字符', trigger: 'blur' }
  ]
}

const handleLogin = async () => {
  if (!formRef.value) return
  const valid = await formRef.value.validate().catch(() => false)
  if (!valid) return

  loading.value = true
  errorMsg.value = ''
  try {
    const res = await request.post('/api/auth/login', form)
    localStorage.setItem('token', res.access_token)
    ElMessage.success('登录成功')
    router.push('/daily-news')
  } catch (e) {
    errorMsg.value = e.response?.data?.detail || e.message || '登录失败'
  }
  loading.value = false
}

const handleRegister = async () => {
  if (!formRef.value) return
  const valid = await formRef.value.validate().catch(() => false)
  if (!valid) return

  regLoading.value = true
  errorMsg.value = ''
  try {
    await request.post('/api/auth/register', form)
    ElMessage.success('注册成功，请登录')
  } catch (e) {
    errorMsg.value = e.response?.data?.detail || e.message || '注册失败'
  }
  regLoading.value = false
}
</script>

<style scoped>
.login-page {
  display: flex;
  justify-content: center;
  align-items: center;
  min-height: 100vh;
  position: relative;
  overflow: hidden;
  /* 天枢 · 清新冷调光晕 */
  background:
    radial-gradient(circle at 16% 18%, rgba(99, 179, 255, 0.28) 0, transparent 46%),
    radial-gradient(circle at 84% 26%, rgba(139, 124, 255, 0.24) 0, transparent 44%),
    radial-gradient(circle at 50% 88%, rgba(77, 211, 234, 0.20) 0, transparent 50%),
    linear-gradient(135deg, #eef4ff 0%, #e4edfe 50%, #ece7fc 100%);
}
html.dark .login-page {
  background:
    radial-gradient(circle at 16% 18%, rgba(90, 140, 255, 0.22) 0, transparent 46%),
    radial-gradient(circle at 84% 26%, rgba(150, 110, 255, 0.18) 0, transparent 44%),
    linear-gradient(135deg, #0a0e1c 0%, #101432 60%, #1a1540 100%);
}
.login-logo {
  width: 56px; height: 56px; margin: 0 auto;
  border-radius: 18px; display: grid; place-items: center;
  font-size: 26px; color: #fff;
  background: linear-gradient(135deg, #4f8ef7 0%, #7c5cff 100%);
  box-shadow: 0 12px 28px -8px rgba(79, 142, 247, 0.6);
}
</style>
