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

    <el-card shadow="never" class="section-card">
      <template #header>动作分布趋势（按动作类型）</template>
      <div class="chart-wrap">
        <div class="chart-block">
          <div class="chart-title">24h 失败登录</div>
          <div class="bars">
            <div
              v-for="b in failedBars24h"
              :key="b.label"
              class="bar-row"
            >
              <span class="bar-label">{{ b.label }}</span>
              <div class="bar-track">
                <div
                  class="bar-fill"
                  :style="{ width: barWidth(b.value, maxFailed24h) }"
                ></div>
              </div>
              <span class="bar-value">{{ b.value }}</span>
            </div>
          </div>
        </div>
        <div class="chart-block">
          <div class="chart-title">7d 失败登录</div>
          <div class="bars">
            <div
              v-for="b in failedBars7d"
              :key="b.label"
              class="bar-row"
            >
              <span class="bar-label">{{ b.label }}</span>
              <div class="bar-track">
                <div
                  class="bar-fill"
                  :style="{ width: barWidth(b.value, maxFailed7d) }"
                ></div>
              </div>
              <span class="bar-value">{{ b.value }}</span>
            </div>
          </div>
        </div>
      </div>
      <div class="chart-compare">
        <span class="compare-label">24h vs 7d 失败登录</span>
        <div class="compare-bars">
          <div class="compare-item">
            <span class="compare-name">24h</span>
            <div class="bar-track">
              <div
                class="bar-fill compare-24h"
                :style="{ width: barWidth(summary.since_24h.failed_logins, maxFailedCompare) }"
              ></div>
            </div>
            <span class="bar-value">{{ summary.since_24h.failed_logins }}</span>
          </div>
          <div class="compare-item">
            <span class="compare-name">7d</span>
            <div class="bar-track">
              <div
                class="bar-fill compare-7d"
                :style="{ width: barWidth(summary.since_7d.failed_logins, maxFailedCompare) }"
              ></div>
            </div>
            <span class="bar-value">{{ summary.since_7d.failed_logins }}</span>
          </div>
        </div>
      </div>
    </el-card>

    <el-row :gutter="16">
      <el-col :span="12">
        <el-card shadow="never">
          <template #header>失败登录 TOP IP</template>
          <el-table :data="failed.top_ips" size="small" border>
            <el-table-column prop="ip" label="IP" />
            <el-table-column prop="count" label="次数" width="80" />
          </el-table>
          <div class="table-hint">可结合下方审计日志按 IP 追溯具体行为</div>
        </el-card>
      </el-col>
      <el-col :span="12">
        <el-card shadow="never">
          <template #header>失败登录 TOP 用户名</template>
          <el-table :data="failed.top_usernames" size="small" border>
            <el-table-column prop="username" label="用户名" />
            <el-table-column prop="count" label="次数" width="80" />
          </el-table>
          <div class="table-hint">可结合下方审计日志按用户名追溯具体行为</div>
        </el-card>
      </el-col>
    </el-row>

    <el-card shadow="never" class="section-card">
      <template #header>
        <div class="card-head">
          <span>IP 黑名单</span>
          <div class="ban-add">
            <el-input
              v-model="banInput.ip"
              placeholder="IPv4 / IPv6"
              style="width: 160px"
              clearable
            />
            <el-input
              v-model="banInput.reason"
              placeholder="原因（可选）"
              style="width: 160px"
              clearable
            />
            <el-button type="danger" :loading="banAdding" @click="onAddBan">拉黑</el-button>
          </div>
        </div>
      </template>
      <el-table :data="ipBans" size="small" border>
        <el-table-column prop="ip" label="IP" min-width="160" />
        <el-table-column prop="reason" label="原因" min-width="160" />
        <el-table-column label="时间" min-width="170">
          <template #default="{ row }">
            {{ formatTime(row.created_at) }}
          </template>
        </el-table-column>
        <el-table-column label="操作" width="90">
          <template #default="{ row }">
            <el-button size="small" type="primary" text @click="onUnban(row)">解封</el-button>
          </template>
        </el-table-column>
      </el-table>
      <div class="table-hint">
        24h 内失败登录达到 20 次的 IP 会被自动拉黑（本地回环地址豁免）；拉黑后该 IP 全站无法访问。
      </div>
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
            @change="onActionChange"
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
      <div class="pager">
        <el-pagination
          layout="total, prev, pager, next"
          :total="logTotal"
          :page-size="logPageSize"
          :current-page="logPage"
          @current-change="onPageChange"
        />
      </div>
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
  actions_by_type: Record<string, number>
}
interface FailedLogins {
  top_ips: { ip: string; count: number }[]
  top_usernames: { username: string; count: number }[]
}
interface LogItem {
  id: number
  user_id: number | null
  action: string
  ip: string | null
  user_agent: string | null
  detail: { username?: string } | null
  created_at: string | null
}
interface LogRow {
  id: number
  action: string
  ip: string
  username: string
  created_at: string
}

const loading = ref(false)
const summary = ref<{ since_24h: SummaryBucket; since_7d: SummaryBucket }>({
  since_24h: { login_attempts: 0, failed_logins: 0, registrations: 0, actions_by_type: {} },
  since_7d: { login_attempts: 0, failed_logins: 0, registrations: 0, actions_by_type: {} },
})
const failed = ref<FailedLogins>({ top_ips: [], top_usernames: [] })
const logs = ref<LogRow[]>([])
const actionFilter = ref('')
const logTotal = ref(0)
const logPage = ref(1)
const logPageSize = 20

interface IpBanRow {
  id: number
  ip: string
  reason: string
  created_at: string | null
}
const ipBans = ref<IpBanRow[]>([])
const banAdding = ref(false)
const banInput = ref({ ip: '', reason: '' })

const summaryCards = computed(() => [
  { label: '24h 登录尝试', value: summary.value.since_24h.login_attempts },
  { label: '24h 失败登录', value: summary.value.since_24h.failed_logins },
  { label: '24h 注册', value: summary.value.since_24h.registrations },
  { label: '7d 登录尝试', value: summary.value.since_7d.login_attempts },
])

// 失败登录按动作类型分布（CSS 柱状图）
const ACTION_LABELS: Record<string, string> = {
  login_failed: '登录失败',
  login: '登录',
  register: '注册',
  points_grant: '发放积分',
  admin_update_user: '管理更新',
}

function toBars(bucket: SummaryBucket): { label: string; value: number }[] {
  const entries = Object.entries(bucket.actions_by_type || {}).sort((a, b) => b[1] - a[1])
  if (entries.length === 0) return [{ label: '暂无数据', value: 0 }]
  return entries.map(([k, v]) => ({ label: ACTION_LABELS[k] ?? k, value: v }))
}

const failedBars24h = computed(() => toBars(summary.value.since_24h))
const failedBars7d = computed(() => toBars(summary.value.since_7d))
const maxFailed24h = computed(() =>
  Math.max(1, ...failedBars24h.value.map((b) => b.value)),
)
const maxFailed7d = computed(() =>
  Math.max(1, ...failedBars7d.value.map((b) => b.value)),
)
const maxFailedCompare = computed(() =>
  Math.max(1, summary.value.since_24h.failed_logins, summary.value.since_7d.failed_logins),
)

function barWidth(value: number, max: number): string {
  return `${Math.max(2, Math.round((value / max) * 100))}%`
}

async function loadSummary() {
  const { data } = await http.get('/admin/traffic/summary')
  summary.value = data
}
async function loadFailed() {
  const { data } = await http.get<FailedLogins>('/admin/traffic/failed-logins')
  failed.value = data
}
async function loadLogs() {
  const params: Record<string, unknown> = {
    page: logPage.value,
    page_size: logPageSize,
  }
  if (actionFilter.value) params.action = actionFilter.value
  const { data } = await http.get('/admin/traffic/logs', { params })
  logTotal.value = data.total
  logs.value = data.items.map((it: LogItem) => ({
    id: it.id,
    action: it.action,
    ip: it.ip,
    username: it.detail?.username ?? '',
    created_at: it.created_at,
  }))
}

function onActionChange() {
  logPage.value = 1
  loadLogs()
}
function onPageChange(page: number) {
  logPage.value = page
  loadLogs()
}

async function loadIpBans() {
  try {
    const { data } = await http.get<IpBanRow[]>('/admin/ip-bans')
    ipBans.value = data
  } catch {
    ipBans.value = []
  }
}

async function onAddBan() {
  const ip = banInput.value.ip.trim()
  if (!ip) {
    ElMessage.warning('请输入要拉黑的 IP')
    return
  }
  banAdding.value = true
  try {
    await http.post('/admin/ip-bans', {
      ip,
      reason: banInput.value.reason.trim(),
    })
    ElMessage.success('已加入黑名单')
    banInput.value = { ip: '', reason: '' }
    await loadIpBans()
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || '拉黑失败')
  } finally {
    banAdding.value = false
  }
}

async function onUnban(row: IpBanRow) {
  try {
    await http.delete(`/admin/ip-bans/${row.id}`)
    ElMessage.success('已解封')
    await loadIpBans()
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || '解封失败')
  }
}

function formatTime(iso: string | null): string {
  if (!iso) return '-'
  const d = new Date(iso)
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleString()
}

async function loadAll() {
  loading.value = true
  try {
    await Promise.all([loadSummary(), loadFailed(), loadLogs(), loadIpBans()])
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || '加载流量数据失败')
  } finally {
    loading.value = false
  }
}

onMounted(() => {
  loadAll()
})
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
  gap: 12px;
  flex-wrap: wrap;
}
.ban-add {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}
.chart-wrap {
  display: flex;
  gap: 32px;
  flex-wrap: wrap;
}
.chart-block {
  flex: 1;
  min-width: 260px;
}
.chart-title {
  font-size: 13px;
  color: #909399;
  margin-bottom: 12px;
}
.bars {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.bar-row {
  display: flex;
  align-items: center;
  gap: 8px;
}
.bar-label {
  width: 80px;
  font-size: 12px;
  color: #606266;
  text-align: right;
  flex-shrink: 0;
}
.bar-track {
  flex: 1;
  height: 14px;
  background: #f0f2f5;
  border-radius: 7px;
  overflow: hidden;
}
.bar-fill {
  height: 100%;
  background: #f56c6c;
  border-radius: 7px;
  transition: width 0.3s ease;
}
.bar-value {
  width: 40px;
  font-size: 12px;
  color: #303133;
  flex-shrink: 0;
}
.chart-compare {
  margin-top: 20px;
  padding-top: 16px;
  border-top: 1px solid #f0f2f5;
}
.compare-label {
  font-size: 13px;
  color: #909399;
  display: block;
  margin-bottom: 12px;
}
.compare-bars {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.compare-item {
  display: flex;
  align-items: center;
  gap: 8px;
}
.compare-name {
  width: 40px;
  font-size: 12px;
  color: #606266;
  flex-shrink: 0;
}
.compare-24h {
  background: #409eff;
}
.compare-7d {
  background: #67c23a;
}
.table-hint {
  margin-top: 8px;
  font-size: 12px;
  color: #909399;
}
.lock-controls {
  display: flex;
  align-items: center;
  gap: 8px;
}
.auto-label {
  font-size: 13px;
  color: #606266;
}
.pager {
  margin-top: 12px;
  display: flex;
  justify-content: flex-end;
}
</style>
