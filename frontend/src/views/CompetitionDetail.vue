<template>
  <div class="comp-detail" v-loading="loading">
    <el-empty v-if="!loading && !competition" description="比赛不存在或已删除" />

    <template v-if="competition">
      <!-- 头部 -->
      <section class="comp-detail__header">
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
            <el-tag size="small" type="warning">{{ gameplayLabel(competition.gameplay_plugin) }}</el-tag>
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
          <el-table-column prop="id" label="ID" width="70" />
          <el-table-column label="参赛形式" width="110">
            <template #default="{ row }">
              {{ participantLabel(row.participant_type) }}
            </template>
          </el-table-column>
          <el-table-column label="参赛者" min-width="160">
            <template #default="{ row }">
              {{ row.team_id ? `队伍#${row.team_id}` : `选手#${row.user_id}` }}
            </template>
          </el-table-column>
          <el-table-column prop="status" label="状态" width="110">
            <template #default="{ row }">
              <el-tag size="small">{{ regStatusLabel(row.status) }}</el-tag>
            </template>
          </el-table-column>
        </el-table>
      </section>

      <!-- 赛程 / 对局列表 -->
      <section class="comp-detail__section">
        <h2>赛程 / 对局</h2>
        <div v-if="rounds.length === 0" class="comp-detail__empty">
          <el-empty description="暂无对局" />
        </div>
        <div v-for="round in rounds" :key="round.round_id" class="comp-detail__round">
          <h3>第 {{ round.round_id }} 轮</h3>
          <div class="comp-detail__matches">
            <el-card
              v-for="m in round.matches"
              :key="m.id"
              class="match-card"
              shadow="hover"
              @click="goMatch(m)"
            >
              <div class="match-card__row">
                <span class="match-card__name">{{ participantName(m.participant_a) }}</span>
                <span class="match-card__vs">VS</span>
                <span class="match-card__name">{{ participantName(m.participant_b) }}</span>
              </div>
              <div class="match-card__foot">
                <el-tag size="small" :type="matchStatusType(m.status)">
                  {{ matchStatusLabel(m.status) }}
                </el-tag>
                <span v-if="m.result" class="match-card__result">{{ resultText(m) }}</span>
              </div>
            </el-card>
          </div>
        </div>
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
          <el-table-column prop="wins" label="胜场" width="90" />
        </el-table>
      </section>
    </template>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import http from '../api/http'
import { useAuthStore } from '../stores/auth'

interface Competition {
  id: number
  name: string
  description: string | null
  banner_url: string | null
  participant_type: string
  tournament_format: string
  format_config: Record<string, any>
  gameplay_plugin: string
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
  status: string
}

interface MatchInfo {
  id: number
  round_id: number
  participant_a: number | null
  participant_b: number | null
  status: string
  result: Record<string, any> | null
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
const loading = ref(false)
const registrations = ref<Registration[]>([])
const regLoading = ref(false)
const rounds = ref<RoundGroup[]>([])
const rankings = ref<RankingRow[]>([])
const rankLoading = ref(false)
const myTeam = ref<TeamInfo | null>(null)
const registering = ref(false)
const withdrawing = ref(false)

const registered = computed(() =>
  registrations.value.some((r) => r.user_id === auth.user?.id)
)
const isFull = computed(
  () =>
    competition.value !== null &&
    registrations.value.length >= competition.value.max_participants
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
  return (STATUS_TYPES[s] as any) || 'info'
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
function gameplayLabel(g: string) {
  if (g === 'triangle_occupy') return '三角占领'
  return g
}
function regStatusLabel(s: string) {
  if (s === 'confirmed') return '已确认'
  if (s === 'pending') return '待确认'
  return s
}
function matchStatusLabel(s: string) {
  if (s === 'in_progress') return '进行中'
  if (s === 'finished') return '已结束'
  return '未开始'
}
function matchStatusType(s: string) {
  if (s === 'in_progress') return 'success'
  if (s === 'finished') return 'info'
  return 'warning'
}
function formatTime(t: string) {
  return new Date(t).toLocaleString('zh-CN')
}

const formatSummary = computed(() => {
  if (!competition.value) return ''
  const f = competition.value.tournament_format
  const cfg = competition.value.format_config || {}
  if (f === 'round_robin') {
    return `循环赛制：所有参赛者分为 ${cfg.group_size ?? 1} 组进行循环对战，组内每对选手均需交手。`
  }
  if (f === 'swiss') {
    return `瑞士轮赛制：共进行 ${cfg.rounds ?? 5} 轮，每轮按积分相近原则配对，积分高者晋级。`
  }
  if (f === 'single_elim') {
    const parts: string[] = ['单败淘汰赛制：输一场即淘汰。']
    if (cfg.seeded) parts.push('采用种子排位。')
    if (cfg.third_place) parts.push('设有季军争夺战。')
    return parts.join('')
  }
  return `赛制：${f}`
})

function participantName(id: number | null) {
  if (id === null) return '待定'
  const reg = registrations.value.find(
    (r) => r.team_id === id || r.user_id === id
  )
  if (reg) return reg.team_id ? `队伍#${reg.team_id}` : `选手#${reg.user_id}`
  return `参赛者#${id}`
}

function resultText(m: MatchInfo) {
  if (!m.result) return ''
  const winner = m.result.winner
  if (winner === null || winner === undefined) return '平局'
  return `胜者：${participantName(Number(winner))}`
}

function goMatch(m: MatchInfo) {
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

onMounted(async () => {
  await auth.fetchMe()
  await loadCompetition()
  await loadRegistrations()
  await loadMatches()
  await loadRankings()
  if (auth.isLoggedIn) await loadMyTeam()
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
.comp-detail__empty {
  padding: 8px 0;
}
.comp-detail__round {
  margin-bottom: 20px;
}
.comp-detail__round h3 {
  margin: 0 0 10px;
  font-size: 16px;
}
.comp-detail__matches {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(260px, 1fr));
  gap: 12px;
}
.match-card {
  cursor: pointer;
}
.match-card__row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  margin-bottom: 10px;
}
.match-card__name {
  flex: 1;
  text-align: center;
  font-weight: 600;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.match-card__vs {
  color: #c0c4cc;
  font-size: 12px;
}
.match-card__foot {
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.match-card__result {
  font-size: 12px;
  color: #909399;
}
</style>
