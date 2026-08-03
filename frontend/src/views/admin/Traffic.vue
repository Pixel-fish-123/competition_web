<template>
  <div class="admin-page">
    <div class="page-head">
      <h2>流量监控</h2>
      <el-button type="primary" :loading="loading" @click="loadAll">刷新</el-button>
    </div>

    <el-row :gutter="16" class="summary-row">
      <el-col :span="6" v-for="c in summaryCards" :key="c.label">
        <el-card shadow="never">
          <div class="summary-label">{{ c.label }}</div>
          <div class="summary-value">{{ c.value }}</div>
        </el-card>
      </el-col>
    </el-row>

    <el-row :gutter="16">
      <el-col :span="12">
        <el-card shadow="never">
          <template #header>失败登录 TOP IP</template>
          <el-table :data="failed.top_ips" size="small" border>
            <el-table-column prop="ip" label="IP" />
            <el-table-column prop="count" label="次数" width="80" />
          </el-table>
        </el-card>
      </el-col>
      <el-col :span="12">
        <el-card shadow="never">
          <template #header>失败登录 TOP 用户名</template>
          <el-table :data="failed.top_usernames" size="small" border>
            <el-table-column prop="username" label="用户名" />
            <el-table-column prop="count" label="次数" width="80" />
          </el-table>
        </el-card>
      </el-col>
    </el-row>

    <el-card shadow="never" class="section-card">
      <template #header>当前锁定账号</template>
      <el-table :data="locked" size="small" border>
        <el-table-column prop="username" label="用户名" />
        <el-table-column prop="remaining_seconds" label="剩余秒数" width="120" />
      </el-table>
    </el-card>

    <el-card shadow="never">
      <template #header>
        <div class="card-head">
          <span>审计日志</span>
          <el-select
            v-model="actionFilter"
            placeholder="按动作过滤"
            clearable
            style="width: 180px"
            @change="loadLogs"
          >
            <el-option label="登录" value="login" />
            <el-option label="登录失败" value="login_failed" />
            <el-option label="注册" value="register" />
            <el-option label="发放积分" value="points_grant" />
            <el-option label="管理更新用户" value="admin_update_user" />
          </el-select>
        </div>
      </template>
      <el-table :data="logs" size="small" border>
        <el-table-column prop="id" label="ID" width="70" />
        <el-table-column prop="action" label="动作" width="140" />
        <el-table-column prop="ip" label="IP" width="140" />
        <el-table-column prop="username" label="用户名" width="120" />
        <el-table-column prop="created_at" label="时间" min-width="180" />
      </el-table>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import http from '../../api/http'

interface SummaryBucket {
  login_attempts: number
  failed_logins: number
  registrations: number
}
interface FailedLogins {
  top_ips: { ip: string; count: number }[]
  top_usernames: { username: string; count: number }[]
}
interface LockedItem {
  username: string
  remaining_seconds: number
}
interface LogItem {
  id: number
  action: string
  ip: string
  username: string
  created_at: string
}

const loading = ref(false)
const summary = ref<{ since_24h: SummaryBucket; since_7d: SummaryBucket }>({
  since_24h: { login_attempts: 0, failed_logins: 0, registrations: 0 },
  since_7d: { login_attempts: 0, failed_logins: 0, registrations: 0 },
})
const failed = ref<FailedLogins>({ top_ips: [], top_usernames: [] })
const locked = ref<LockedItem[]>([])
const logs = ref<LogItem[]>([])
const actionFilter = ref('')

const summaryCards = computed(() => [
  { label: '24h 登录尝试', value: summary.value.since_24h.login_attempts },
  { label: '24h 失败登录', value: summary.value.since_24h.failed_logins },
  { label: '24h 注册', value: summary.value.since_24h.registrations },
  { label: '7d 登录尝试', value: summary.value.since_7d.login_attempts },
])

async function loadSummary() {
  const { data } = await http.get('/admin/traffic/summary')
  summary.value = data
}
async function loadFailed() {
  const { data } = await http.get<FailedLogins>('/admin/traffic/failed-logins')
  failed.value = data
}
async function loadLocked() {
  const { data } = await http.get<LockedItem[]>('/admin/traffic/locked')
  locked.value = data
}
async function loadLogs() {
  const params = actionFilter.value ? { action: actionFilter.value } : {}
  const { data } = await http.get('/admin/traffic/logs', { params })
  logs.value = data.items.map((it: any) => ({
    id: it.id,
    action: it.action,
    ip: it.ip,
    username: it.detail?.username ?? '',
    created_at: it.created_at,
  }))
}

async function loadAll() {
  loading.value = true
  try {
    await Promise.all([loadSummary(), loadFailed(), loadLocked(), loadLogs()])
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || '加载流量数据失败')
  } finally {
    loading.value = false
  }
}

onMounted(loadAll)
</script>

<style scoped>
.admin-page h2 {
  margin-top: 0;
}
.page-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
}
.summary-row {
  margin-bottom: 16px;
}
.summary-label {
  color: #909399;
  font-size: 13px;
}
.summary-value {
  font-size: 24px;
  font-weight: 600;
  margin-top: 4px;
}
.section-card {
  margin: 16px 0;
}
.card-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
</style>
