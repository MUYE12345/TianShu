<template>
  <el-card>
    <template #header><span><el-icon><Message /></el-icon> 推送配置</span></template>
    <el-tabs v-model="activeTab">
      <el-tab-pane label="飞书" name="feishu">
        <el-form label-width="140px">
          <el-form-item label="Webhook URL">
            <el-input v-model="form.feishu.webhook" placeholder="https://open.feishu.cn/open-apis/bot/v2/hook/..." />
          </el-form-item>
          <el-form-item label="Bot Token">
            <el-input v-model="form.feishu.token" type="password" show-password />
          </el-form-item>
          <el-form-item label="App ID"><el-input v-model="form.feishu.app_id" /></el-form-item>
          <el-form-item label="App Secret"><el-input v-model="form.feishu.app_secret" type="password" show-password /></el-form-item>
          <el-form-item>
            <el-button type="primary" @click="testFeishu">测试推送</el-button>
          </el-form-item>
        </el-form>
      </el-tab-pane>
      <el-tab-pane label="QQ邮箱" name="qqmail">
        <el-form label-width="140px">
          <el-form-item label="SMTP主机"><el-input v-model="form.qqmail.host" placeholder="smtp.qq.com" /></el-form-item>
          <el-form-item label="SMTP端口"><el-input-number v-model="form.qqmail.port" :min="1" :max="999" /></el-form-item>
          <el-form-item label="邮箱账号"><el-input v-model="form.qqmail.user" placeholder="your@qq.com" /></el-form-item>
          <el-form-item label="授权码"><el-input v-model="form.qqmail.pass" type="password" show-password /></el-form-item>
          <el-form-item>
            <el-button type="primary" @click="testQQMail">测试发送</el-button>
          </el-form-item>
        </el-form>
      </el-tab-pane>
    </el-tabs>
  </el-card>
</template>

<script setup>
import { reactive, ref, onMounted } from 'vue'
import request from '../../utils/request'
import { ElMessage } from 'element-plus'

const activeTab = ref('feishu')
const form = reactive({
  feishu: { webhook: '', token: '', app_id: '', app_secret: '' },
  qqmail: { host: 'smtp.qq.com', port: 465, user: '', pass: '' }
})

onMounted(async () => {
  try {
    const res = await request.get('/api/notify/config')
    if (res) {
      form.feishu.webhook = res.feishu_url || ''
      form.qqmail.host = res.qqmail_host || 'smtp.qq.com'
      form.qqmail.user = res.qqmail_user || ''
    }
  } catch {}
})

const testFeishu = async () => {
  try {
    const res = await request.post('/api/notify/test/feishu')
    ElMessage.success(res.success ? '发送成功' : '发送失败')
  } catch { ElMessage.error('测试失败') }
}

const testQQMail = async () => {
  try {
    const res = await request.post('/api/notify/test/qqmail')
    ElMessage.success(res.success ? '发送成功' : '发送失败')
  } catch { ElMessage.error('测试失败') }
}

</script>
