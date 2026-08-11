<template>
  <div class="comp-detail" v-loading="loading">
    <el-empty v-if="!loading && !competition" description="比赛不存在或已删除" />

    <template v-if="competition">
      <!-- 头部 -->
      <section class="comp-detail__header">
        <div class="comp-detail__back">
          <el-button text @click="router.back()">← 返回比赛列表</el-button>
        </div>
        <div class="comp-detail__banner" :class="`banner-${(competition.id % 4) + 1}`">
          <span>{{ competition.name }}</span>
        </div>
        <div class="comp-detail__info">
          <div class="comp-detail__title-row">
            <h1>{{ competition.name }}</h1>
            <el-tag :type="statusType(competition.status)" effect="dark">
              {{ statusLabel(competition.status) }}
            </el-tag>
          </div>
          <p class="comp-detail__desc">{{ competition.description || '暂无描述' }}</p>
          <div class="comp-detail__meta">
            <el-tag size="small">{{ participantLabel(competition.participant_type) }}</el-tag>
            <el-tag size="small" type="success">{{ formatLabel(competition.tournament_format) }}</el-tag>
            <el-tag size="small" type="info">上限 {{ competition.max_participants }}</el-tag>
          </div>
          <div class="comp-detail__time">
            <span v-if="competition.start_time">开始：{{ formatTime(competition.start_time) }}</span>
            <span v-if="competition.end_time">结束：{{ formatTime(competition.end_time) }}</span>
          </div>
        </div>
      </section>

      <!-- 赛制说明 -->
      <section class="comp-detail__section">
        <h2>赛制说明</h2>
        <el-alert
          :title="formatSummary"
          type="info"
          :closable="false"
          show-icon
        />
      </section>

      <!-- 报名区 -->
      <section v-if="competition.status === 'registration'" class="comp-detail__section">
        <h2>报名</h2>
        <div v-if="!auth.isLoggedIn" class="comp-detail__register">
          <el-button type="primary" @click="$router.push('/login')">登录后报名</el-button>
        </div>
        <div v-else-if="registered" class="comp-detail__register">
          <el-tag type="success" size="large">已报名</el-tag>
          <el-button type="danger" plain :loading="withdrawing" @click="onWithdraw">
            撤销报名
          </el-button>
        </div>
        <div v-else-if="isFull" class="comp-detail__register">
          <el-button type="primary" disabled>名额已满</el-button>
        </div>
        <div v-else class="comp-detail__register">
          <el-button
            v-if="competition.participant_type !== 'team'"
            type="primary"
            :loading="registering"
            @click="onRegister('individual')"
          >
            个人报名
          </el-button>
          <el-button
            v-if="competition.participant_type !== 'individual'"
            type="success"
            :loading="registering"
            @click="onRegister('team')"
          >
            队伍报名
          </el-button>
          <span v-if="competition.participant_type === 'team' && !myTeam" class="comp-detail__hint">
            暂无队伍，请先
            <el-button text type="primary" @click="$router.push('/profile')">创建队伍</el-button>
          </span>
        </div>
      </section>

      <!-- 参赛名单 -->
      <section class="comp-detail__section">
        <h2>参赛名单</h2>
        <el-table :data="registrations" v-loading="regLoading" border stripe>
          <el-table-column label="参赛形式" width="110">
            <template #default="{ row }">
              {{ participantLabel(row.participant_type) }}
            </template>
          </el-table-column>
          <el-table-column label="参赛者" min-width="160">
            <template #default="{ row }">
              {{ row.participant_name || '未知' }}
            </template>
          </el-table-column>
          <el-table-column prop="status" label="状态" width="110">
            <template #default="{ row }">
              <el-tag size="small">{{ regStatusLabel(row.status) }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column
            v-if="auth.user?.role === 'admin'"
            label="操作"
            width="140"
          >
            <template #default="{ row }">
              <template v-if="row.status === 'pending'">
                <el-button
                  type="success"
                  size="small"
                  :loading="reviewingId === row.id"
                  @click="reviewRegistration(row.id, 'approve')"
                >
                  通过
                </el-button>
                <el-button
                  type="danger"
                  size="small"
                  :loading="reviewingId === row.id"
                  @click="reviewRegistration(row.id, 'reject')"
                >
                  拒绝
                </el-button>
              </template>
            </template>
          </el-table-column>
        </el-table>
      </section>

      <!-- 赛程 / 对局列表 -->
      <section class="comp-detail__section">
        <div class="comp-detail__section-head">
          <h2>赛程 / 对局</h2>
          <div
            v-if="competition.status === 'ongoing' && auth.isRefereeOrAdmin && rounds.length > 0"
            class="comp-detail__round-actions"
          >
            <el-button
              v-if="latestRoundFinished && !latestRoundLocked"
              size="small"
              type="warning"
              :loading="completingRound"
              @click="onCompleteLatestRound"
            >
              开始下一轮
            </el-button>
            <el-button
              size="small"
              plain
              :disabled="latestRoundLocked"
              :loading="resettingRound"
              @click="onResetLatestRound"
            >
              重置最新一轮
            </el-button>
          </div>
        </div>
        <ScheduleChart
          :rounds="rounds"
          :format="competition.tournament_format"
          @select="goMatch"
        />
      </section>

      <!-- 场次排名 -->
      <section class="comp-detail__section">
        <h2>场次排名</h2>
        <el-table :data="rankings" v-loading="rankLoading" border stripe>
          <el-table-column prop="rank" label="排名" width="80" />
          <el-table-column label="参赛者" min-width="160">
            <template #default="{ row }">
              {{ row.participant_name || `参赛者#${row.participant_id}` }}
            </template>
          </el-table-column>
          <el-table-column prop="wins" label="胜场" width="80" />
          <el-table-column prop="losses" label="败场" width="80" />
          <el-table-column prop="draws" label="平局" width="80" />
          <el-table-column prop="points" label="积分" width="80" />
        </el-table>
      </section>
    </template>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import http from '../api/http'
import { useAuthStore } from '../stores/auth'
import ScheduleChart from '../components/ScheduleChart.vue'

interface Competition {
  id: number
  name: string
  description: string | null
  banner_url: string | null
  participant_type: string
  tournament_format: string
  format_config: Record<string, any>
  max_participants: number
  status: string
  start_time: string | null
  end_time: string | null
}

interface Registration {
  id: number
  competition_id: number
  user_id: number | null
  team_id: number | null
  participant_type: string
  participant_name?: string | null
  status: string
}

interface MatchInfo {
  id: number
  round_id: number
  participant_a: number | null
  participant_b: number | null
  participant_a_name?: string | null
  participant_b_name?: string | null
  status: string
  result: Record<string, any> | null
  result_locked: boolean
}

interface RoundGroup {
  round_id: number
  matches: MatchInfo[]
}

interface RankingRow {
  rank: number
  participant_id: number
  participant_name?: string
  wins: number
  losses: number
  draws: number
  points: number
}

interface TeamInfo {
  id: number
  name: string
}

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()

const cid = computed(() => Number(route.params.cid))

const competition = ref<Competition | null>(null)
const loading = ref(true)
const registrations = ref<Registration[]>([])
const regLoading = ref(false)
const rounds = ref<RoundGroup[]>([])
const rankings = ref<RankingRow[]>([])
const rankLoading = ref(false)
const myTeam = ref<TeamInfo | null>(null)
const registering = ref(false)
const withdrawing = ref(false)
const reviewingId = ref<number | null>(null)
const completingRound = ref(false)
const resettingRound = ref(false)

// 最新一轮及其真实对局是否全部结束 / 是否已锁定。
const latestRound = computed(() => {
  if (rounds.value.length === 0) return null
  return [...rounds.value].sort((a, b) => b.round_id - a.round_id)[0]
})
const latestRoundFinished = computed(() => {
  const round = latestRound.value
  if (!round) return false
  const real = round.matches.filter((m) => m.participant_b !== null)
  return real.length > 0 && real.every((m) => m.status === 'finished')
})
const latestRoundLocked = computed(() => {
  const round = latestRound.value
  if (!round) return false
  return round.matches.some((m) => m.result_locked)
})

// 是否已报名：个人报名匹配 user_id；队伍报名匹配 team_id（报名行存队长
// user_id，非队长成员需靠 team_id 判断）。rejected 不算已报名。
const registered = computed(() =>
  registrations.value.some(
    (r) =>
      r.status !== 'rejected' &&
      (r.user_id === auth.user?.id ||
        (r.team_id !== null && r.team_id === myTeam.value?.id)),
  )
)
// 是否满员：只计 pending + approved（与后端 _approved_count 一致），rejected 不占名额。
const isFull = computed(
  () =>
    competition.value !== null &&
    registrations.value.filter((r) => r.status === 'pending' || r.status === 'approved')
      .length >= competition.value.max_participants,
)

const STATUS_LABELS: Record<string, string> = {
  draft: '草稿',
  registration: '报名中',
  ongoing: '进行中',
  finished: '已结束',
  cancelled: '已取消',
}
const STATUS_TYPES: Record<string, string> = {
  draft: 'info',
  registration: 'warning',
  ongoing: 'success',
  finished: '',
  cancelled: 'danger',
}

function statusLabel(s: string) {
  return STATUS_LABELS[s] || s
}
function statusType(s: string) {
  return STATUS_TYPES[s] || 'info'
}
function participantLabel(t: string) {
  if (t === 'team') return '团队赛'
  if (t === 'individual') return '个人赛'
  if (t === 'mixed') return '混合赛'
  return t
}
function formatLabel(f: string) {
  if (f === 'round_robin') return '循环赛'
  if (f === 'swiss') return '瑞士轮'
  if (f === 'single_elim') return '单败淘汰'
  return f
}
function regStatusLabel(s: string) {
  if (s === 'pending') return '待审核'
  if (s === 'approved') return '已通过'
  if (s === 'rejected') return '已拒绝'
  return s
}
function formatTime(t: string) {
  return new Date(t).toLocaleString('zh-CN')
}

const formatSummary = computed(() => {
  if (!competition.value) return ''
  const f = competition.value.tournament_format
  if (f === 'swiss') {
    return '瑞士轮赛制：轮数随参赛人数自动调整（ceil(log₂n)+1 轮），每轮按积分相近原则配对，积分高者胜。'
  }
  if (f === 'single_elim') {
    const cfg = competition.value.format_config || {}
    const parts: string[] = ['单败淘汰赛制：输一场即淘汰。']
    if (cfg.seeded) parts.push('采用种子排位。')
    if (cfg.third_place) parts.push('设有季军争夺战。')
    return parts.join('')
  }
  return `赛制：${f}`
})

function goMatch(m: { id: number }) {
  router.push(`/competitions/${cid.value}/matches/${m.id}`)
}

async function loadCompetition() {
  loading.value = true
  try {
    const { data } = await http.get<Competition>(`/competitions/${cid.value}`)
    competition.value = data
  } catch {
    competition.value = null
  } finally {
    loading.value = false
  }
}

async function loadRegistrations() {
  regLoading.value = true
  try {
    const { data } = await http.get<Registration[]>(
      `/competitions/${cid.value}/registrations`
    )
    registrations.value = data
  } catch {
    registrations.value = []
  } finally {
    regLoading.value = false
  }
}

async function loadMatches() {
  try {
    const { data } = await http.get<MatchInfo[]>(`/competitions/${cid.value}/matches`)
    const map = new Map<number, MatchInfo[]>()
    for (const m of data) {
      if (!map.has(m.round_id)) map.set(m.round_id, [])
      map.get(m.round_id)!.push(m)
    }
    rounds.value = Array.from(map.entries())
      .sort((a, b) => a[0] - b[0])
      .map(([round_id, matches]) => ({ round_id, matches }))
  } catch {
    rounds.value = []
  }
}

async function loadRankings() {
  rankLoading.value = true
  try {
    const { data } = await http.get<RankingRow[]>(`/rankings/competition/${cid.value}`)
    rankings.value = data
  } catch {
    rankings.value = []
  } finally {
    rankLoading.value = false
  }
}

async function loadMyTeam() {
  try {
    const { data } = await http.get<{ team: TeamInfo | null }>('/teams/my')
    myTeam.value = data.team
  } catch {
    myTeam.value = null
  }
}

async function onRegister(type: 'individual' | 'team') {
  if (type === 'team' && !myTeam.value) {
    ElMessage.warning('请先创建队伍')
    return
  }
  registering.value = true
  try {
    await http.post(`/competitions/${cid.value}/register`, {
      participant_type: type,
      team_id: type === 'team' ? myTeam.value?.id : undefined,
    })
    ElMessage.success('报名成功')
    await loadRegistrations()
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || '报名失败')
  } finally {
    registering.value = false
  }
}

async function onWithdraw() {
  withdrawing.value = true
  try {
    await http.delete(`/competitions/${cid.value}/register`)
    ElMessage.success('已撤销报名')
    await loadRegistrations()
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || '撤销失败')
  } finally {
    withdrawing.value = false
  }
}

async function reviewRegistration(rid: number, action: 'approve' | 'reject') {
  reviewingId.value = rid
  try {
    await http.post(`/admin/competitions/${cid.value}/registrations/${rid}/${action}`)
    ElMessage.success(action === 'approve' ? '已通过该报名' : '已拒绝该报名')
    await loadRegistrations()
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || '操作失败')
  } finally {
    reviewingId.value = null
  }
}

async function onCompleteLatestRound() {
  const round = latestRound.value
  if (!round) return
  completingRound.value = true
  try {
    const { data } = await http.post<{ locked: number; next_round_id: number | null }>(
      `/competitions/${cid.value}/rounds/${round.round_id}/complete`,
    )
    if (data.next_round_id === null) {
      ElMessage.success(`已锁定本轮 ${data.locked} 场结果，所有轮次已结束`)
    } else {
      ElMessage.success(`已锁定本轮 ${data.locked} 场结果，第 ${data.next_round_id} 轮已生成`)
    }
    await loadMatches()
    await loadRankings()
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || '操作失败')
  } finally {
    completingRound.value = false
  }
}

async function onResetLatestRound() {
  try {
    await ElMessageBox.confirm(
      '将删除最新一轮的全部对局并重新生成（该轮已锁定的结果会被拒绝）。排行榜将按新赛程重新计算。',
      '重置最新一轮',
      { type: 'warning', confirmButtonText: '重置', cancelButtonText: '取消' },
    )
  } catch {
    return
  }
  resettingRound.value = true
  try {
    const { data } = await http.post<{ round_id: number; match_count: number }>(
      `/competitions/${cid.value}/rounds/latest/reset`,
    )
    ElMessage.success(`已重置第 ${data.round_id} 轮，重新生成 ${data.match_count} 场对局`)
    await loadMatches()
    await loadRankings()
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || '重置失败')
  } finally {
    resettingRound.value = false
  }
}

onMounted(async () => {
  await auth.fetchMe()
  await loadCompetition()
  await loadRegistrations()
  await loadMatches()
  await loadRankings()
  if (auth.isLoggedIn) await loadMyTeam()
})

// 组件复用时（cid 变化）重新加载数据，避免展示陈旧内容
watch(() => route.params.cid, async (newCid) => {
  if (newCid) {
    await loadCompetition()
    await loadRegistrations()
    await loadMatches()
    await loadRankings()
    if (auth.isLoggedIn) await loadMyTeam()
  }
})
</script>

<style scoped>
.comp-detail {
  max-width: 1100px;
  margin: 0 auto;
  min-height: 300px;
}
.comp-detail__header {
  display: flex;
  gap: 24px;
  margin-bottom: 24px;
  flex-wrap: wrap;
}
.comp-detail__banner {
  width: 320px;
  height: 180px;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #fff;
  font-size: 24px;
  font-weight: 600;
  border-radius: 8px;
  flex-shrink: 0;
}
.banner-1 {
  background: linear-gradient(135deg, #409eff, #79bbff);
}
.banner-2 {
  background: linear-gradient(135deg, #67c23a, #95d475);
}
.banner-3 {
  background: linear-gradient(135deg, #e6a23c, #f3d19e);
}
.banner-4 {
  background: linear-gradient(135deg, #f56c6c, #f89898);
}
.comp-detail__info {
  flex: 1;
  min-width: 280px;
}
.comp-detail__title-row {
  display: flex;
  align-items: center;
  gap: 12px;
}
.comp-detail__title-row h1 {
  margin: 0;
  font-size: 26px;
}
.comp-detail__desc {
  color: #606266;
  margin: 12px 0;
}
.comp-detail__meta {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}
.comp-detail__time {
  margin-top: 12px;
  display: flex;
  gap: 16px;
  color: #909399;
  font-size: 13px;
}
.comp-detail__section {
  margin-bottom: 32px;
}
.comp-detail__section-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  flex-wrap: wrap;
}
.comp-detail__section-head h2 {
  font-size: 20px;
  margin: 0;
  border-left: 4px solid #409eff;
  padding-left: 10px;
}
.comp-detail__round-actions {
  display: flex;
  gap: 8px;
}
.comp-detail__section h2 {
  font-size: 20px;
  margin: 0 0 12px;
  border-left: 4px solid #409eff;
  padding-left: 10px;
}
.comp-detail__register {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
}
.comp-detail__hint {
  color: #909399;
  font-size: 13px;
}
</style>
