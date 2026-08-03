import axios from 'axios'
import { ElMessage } from 'element-plus'

// Shared axios instance for the frontend.
// baseURL '/api' is proxied to the backend by Vite (see vite.config.ts).
const http = axios.create({
  baseURL: '/api',
  withCredentials: true,
})

// Global response interceptor: surface auth/rate-limit errors consistently.
// 401 → redirect to login; 403 → insufficient permission; 429 → rate limited.
http.interceptors.response.use(
  (response) => response,
  (error) => {
    const status = error.response?.status
    if (status === 401) {
      // Session expired / not authenticated. Redirect to login preserving intent.
      if (window.location.pathname !== '/login') {
        const redirect = encodeURIComponent(
          window.location.pathname + window.location.search,
        )
        window.location.href = `/login?redirect=${redirect}`
      }
    } else if (status === 403) {
      ElMessage.error('权限不足')
    } else if (status === 429) {
      ElMessage.error('请求过于频繁')
    }
    return Promise.reject(error)
  },
)

export default http
