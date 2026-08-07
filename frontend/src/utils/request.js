import axios from 'axios'
import { ElMessage } from 'element-plus'
import router from '../router/index.js'

const request = axios.create({
  baseURL: '',  // 使用相对路径，Vite 开发代理转发 /api → localhost:8000
  timeout: 30000,
})

// 请求拦截器：自动注入 JWT Token
request.interceptors.request.use(
  config => {
    const token = localStorage.getItem('token')
    if (token) {
      config.headers.Authorization = `Bearer ${token}`
    }
    return config
  },
  error => Promise.reject(error)
)

// 响应拦截器：统一错误处理 + 401 自动跳转登录
request.interceptors.response.use(
  response => response.data,
  error => {
    if (error.response?.status === 401) {
      // Token 过期或无效，清除本地 Token 并跳转登录
      localStorage.removeItem('token')
      localStorage.removeItem('username')
      localStorage.removeItem('user_id')
      router.push('/login')
      ElMessage.warning('登录已过期，请重新登录')
      return Promise.reject(error)
    }

    const msg = error.response?.data?.detail || error.response?.data?.message || error.message
    ElMessage.error(typeof msg === 'string' ? msg : '请求失败')
    return Promise.reject(error)
  }
)

export default request
