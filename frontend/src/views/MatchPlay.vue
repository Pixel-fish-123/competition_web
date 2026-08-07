<template>
  <div class="match-play">
    <div class="match-play__header">
      <el-button text @click="goBack">← 返回</el-button>
      <h1>对局 #{{ matchId }}</h1>
      <el-tag v-if="match" :type="matchStatusType" effect="dark" size="large">
        {{ matchStatusText }}
      </el-tag>
      <el-tag v-if="match?.result_locked" type="success" effect="dark" size="large">
        结果已锁定
      </el-tag>
    </div>

    <!-- 状态一：等待开赛 -->
    <div v-if="match && match.status === 'pending'" class="match-play__state">
      <div class="match-play__teams">
        <div class="match-play__team match-play__team--red">
          <span class="match-play__team-label">掠夺者</span>
          <span class="match-play__team-name">{{ raiderName }}</span>
        </div>
        <div class="match-play__vs">VS</div>
        <div class="match-play__team match-play__team--blue">
          <span class="match-play__team-label">守护者</span>
          <span class="match-play__team-name">{{ guardianName }}</span>
        </div>
      </div>

      <div v-if="isRefereeOrAdmin" class="match-play__action">
        <el-button size="large" :loading="randomizingSides" @click="onRandomizeSides">
          随机选边
        </el-button>
        <el-button type="primary" size="large" :loading="starting" @click="onStartMatch">
          开始对局
        </el-button>
      </div>
      <el-alert
        v-else
        type="info"
        :closable="false"
        title="等待裁判开赛"
        description="对局尚未开始，请耐心等待裁判操作。"
        class="match-play__notice"
      />
    </div>

    <!-- 状态二：正在进行 -->
    <div v-else-if="match && match.status === 'in_progress'" class="match-play__state">
      <div class="match-play__live">
        <span class="match-play__live-dot" />
        <span class="match-play__live-text">比赛进行中</span>
      </div>

      <div class="match-play__teams">
        <div class="match-play__team match-play__team--red">
          <span class="match-play__team-label">掠夺者</span>
          <span class="match-play__team-name">{{ raiderName }}</span>
        </div>
        <div class="match-play__vs">VS</div>
        <div class="match-play__team match-play__team--blue">
          <span class="match-play__team-label">守护者</span>
          <span class="match-play__team-name">{{ guardianName }}</span>
        </div>
      </div>

      <div v-if="isRefereeOrAdmin" class="match-play__action">
        <el-button type="danger" size="large" @click="openJudgePanel">
          结束比赛
        </el-button>
      </div>
      <el-alert
        v-else
        type="info"
        :closable="false"
        title="比赛进行中，等待裁判结束"
        class="match-play__notice"
      />

      <!-- 判定面板：导入日志 -> 自动判定 -> 人工微调 -> 保存结果(锁定) -->
      <section v-if="judgeOpen" class="match-play__section">
        <h2 class="match-play__section-title">判定结果</h2>

        <div class="match-play__import">
          <input
            ref="fileInput"
            type="file"
            accept=".json,.csv"
            class="match-play__file-input"
            @change="onFileChange"
          />
          <el-checkbox v-model="syncScores">导入时同步判定</el-checkbox>
          <el-button
            type="primary"
            :disabled="!selectedFile"
            :loading="importing"
            @click="onImportLog"
          >
            导入玩法日志
          </el-button>
          <span v-if="selectedFile" class="match-play__file-name">{{ selectedFile.name }}</span>
        </div>

        <div class="match-play__log-summary" v-if="match.gameplay_log">
          <div class="match-play__log-scores">
            日志判定: 守护者 {{ formatScore(logScores.defender) }} :
            {{ formatScore(logScores.attacker) }} 掠夺者
          </div>
          <div class="match-play__log-winner">
            日志胜者: <el-tag :type="logWinnerTagType" size="small">{{ logWinnerText }}</el-tag>
          </div>
        </div>
        <el-alert
          v-else
          type="info"
          :closable="false"
          title="尚未导入玩法日志"
          description="请先导入 demo 控制器导出的日志文件，系统将自动判定比分与胜者；如结果有误可手动修改后保存。"
          class="match-play__notice"
        />

        <el-form label-width="90px" class="match-play__form">
          <el-form-item label="掠夺者得分">
            <el-input-number v-model="resultForm.score_a" :min="0" :step="1" />
          </el-form-item>
          <el-form-item label="守护者得分">
            <el-input-number v-model="resultForm.score_b" :min="0" :step="1" />
          </el-form-item>
          <el-form-item label="胜者">
            <el-radio-group v-model="resultForm.winner">
              <el-radio :value="'raider'">掠夺者</el-radio>
              <el-radio :value="'guardian'">守护者</el-radio>
              <el-radio :value="'draw'">平局</el-radio>
            </el-radio-group>
          </el-form-item>
        </el-form>
        <div class="match-play__action">
          <el-button @click="judgeOpen = false">取消</el-button>
          <el-button type="primary" :loading="submittingResult" @click="onSaveResult">
            保存结果
          </el-button>
        </div>
        <div class="match-play__lock-hint">保存后结果将锁定，无法再更改</div>
      </section>
    </div>

    <!-- 状态三：已结束 -->
    <div v-else-if="match && match.status === 'finished'" class="match-play__state">
      <!-- 3a. 结果展示 -->
      <section class="match-play__section">
        <h2 class="match-play__section-title">比赛结果</h2>
        <div v-if="match.result" class="match-play__result">
          <div class="match-play__result-line">
            <span class="match-play__result-team match-play__result-team--red">
              {{ raiderName }}
            </span>
            <span class="match-play__result-score">
              {{ formatScore(match.result.score_a) }} : {{ formatScore(match.result.score_b) }}
            </span>
            <span class="match-play__result-team match-play__result-team--blue">
              {{ guardianName }}
            </span>
          </div>
          <div class="match-play__result-winner">
            <el-tag :type="winnerTagType" effect="light">
              {{ winnerText }}
            </el-tag>
          </div>
        </div>
        <el-empty v-else description="待录入结果" :image-size="60" />
        <div v-if="match.result_locked" class="match-play__lock-badge">
          结果已锁定，无法更改
        </div>
        <div v-else-if="isRefereeOrAdmin" class="match-play__action">
          <el-button type="warning" @click="openJudgePanel">修改结果</el-button>
        </div>
      </section>

      <!-- 判定面板（已结束且未锁定时修改结果用） -->
      <section
        v-if="judgeOpen && !match.result_locked && isRefereeOrAdmin"
        class="match-play__section"
      >
        <h2 class="match-play__section-title">修改结果</h2>
        <div class="match-play__import">
          <input
            ref="fileInput"
            type="file"
            accept=".json,.csv"
            class="match-play__file-input"
            @change="onFileChange"
          />
          <el-checkbox v-model="syncScores">导入时同步判定</el-checkbox>
          <el-button
            type="primary"
            :disabled="!selectedFile"
            :loading="importing"
            @click="onImportLog"
          >
            导入玩法日志
          </el-button>
          <span v-if="selectedFile" class="match-play__file-name">{{ selectedFile.name }}</span>
        </div>
        <el-form label-width="90px" class="match-play__form">
          <el-form-item label="掠夺者得分">
            <el-input-number v-model="resultForm.score_a" :min="0" :step="1" />
          </el-form-item>
          <el-form-item label="守护者得分">
            <el-input-number v-model="resultForm.score_b" :min="0" :step="1" />
          </el-form-item>
          <el-form-item label="胜者">
            <el-radio-group v-model="resultForm.winner">
              <el-radio :value="'raider'">掠夺者</el-radio>
              <el-radio :value="'guardian'">守护者</el-radio>
              <el-radio :value="'draw'">平局</el-radio>
            </el-radio-group>
          </el-form-item>
        </el-form>
        <div class="match-play__action">
          <el-button @click="judgeOpen = false">取消</el-button>
          <el-button type="primary" :loading="submittingResult" @click="onSaveResult">
            保存结果
          </el-button>
        </div>
        <div class="match-play__lock-hint">保存后结果将锁定，无法再更改</div>
      </section>

      <!-- 3b. 玩法日志展示（所有用户） -->
      <section v-if="match.gameplay_log" class="match-play__section">
        <h2 class="match-play__section-title">玩法日志</h2>
        <div class="match-play__log-summary">
          <div class="match-play__log-scores">
            日志分数: 守护者 {{ formatScore(logScores.defender) }} :
            {{ formatScore(logScores.attacker) }} 掠夺者
          </div>
          <div class="match-play__log-winner">
            日志判定: <el-tag :type="logWinnerTagType" size="small">{{ logWinnerText }}</el-tag>
          </div>
          <div v-if="logImportedAt" class="match-play__log-time">
            导入时间: {{ formatTime(logImportedAt) }}
          </div>
        </div>
        <div class="match-play__timeline">
          <div
            v-for="(ev, idx) in logEvents"
            :key="idx"
            class="match-play__event"
            :class="`match-play__event--${eventTypeClass(ev.type)}`"
          >
            <span class="match-play__event-time">{{ ev.time }}</span>
            <span class="match-play__event-text">{{ ev.text }}</span>
          </div>
        </div>
      </section>
    </div>

    <!-- 加载中 -->
    <div v-else class="match-play__empty">
      <el-empty description="连接中…" />
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import http from '../api/http'
import { useAuthStore } from '../stores/auth'

interface MatchResult {
  winner: number | null
  is_draw: boolean
  score_a: number
  score_b: number
}

interface GameplayEvent {
  time: string
  type: string
  text: string
}

interface GameplayLog {
  events: GameplayEvent[]
  scores: { defender: number | null; attacker: number | null }
  winner: string | null
  imported_at: string | null
}

interface MatchInfo {
  id: number
  competition_id: number
  round_id: number
  participant_a: number | null
  participant_b: number | null
  participant_a_name: string | null
  participant_b_name: string | null
  status: string
  result: MatchResult | null
  result_type: string | null
  result_locked: boolean
  referee_id: number | null
  gameplay_log: GameplayLog | null
}

interface MatchDetailResp {
  match: MatchInfo
}

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()

const matchId = computed(() => Number(route.params.mid))

const match = ref<MatchInfo | null>(null)
const starting = ref(false)
const randomizingSides = ref(false)
const submittingResult = ref(false)
const importing = ref(false)
const importSuccess = ref(false)

const judgeOpen = ref(false)
const resultForm = reactive<{
  score_a: number
  score_b: number
  winner: 'raider' | 'guardian' | 'draw'
}>({
  score_a: 0,
  score_b: 0,
  winner: 'raider',
})

const fileInput = ref<HTMLInputElement | null>(null)
const selectedFile = ref<File | null>(null)
const syncScores = ref(true)

let ws: WebSocket | null = null
let reconnectTimer: ReturnType<typeof setTimeout> | null = null
let unmounted = false

const isRefereeOrAdmin = computed(() => auth.isRefereeOrAdmin)

// 约定（用户确认）：participant_a = 掠夺者（进攻方/attacker/红方），
// participant_b = 守护者（防守方/defender/蓝方）；页面统一标注掠夺者/守护者。
const raiderName = computed(() => match.value?.participant_a_name || '选手A')
const guardianName = computed(() => match.value?.participant_b_name || '选手B')

const matchStatusType = computed(() => {
  switch (match.value?.status) {
    case 'in_progress':
      return 'success'
    case 'finished':
      return 'info'
    default:
      return 'warning'
  }
})

const matchStatusText = computed(() => {
  switch (match.value?.status) {
    case 'in_progress':
      return '进行中'
    case 'finished':
      return '已结束'
    default:
      return '未开始'
  }
})

const winnerText = computed(() => {
  const r = match.value?.result
  if (!r) return '待录入结果'
  if (r.is_draw) return '平局'
  if (r.winner === match.value?.participant_a) return `掠夺者 ${raiderName.value} 获胜`
  if (r.winner === match.value?.participant_b) return `守护者 ${guardianName.value} 获胜`
  return '结果待定'
})

const winnerTagType = computed(() => {
  const r = match.value?.result
  if (!r) return 'info'
  if (r.is_draw) return 'warning'
  if (r.winner === match.value?.participant_a) return 'danger'
  if (r.winner === match.value?.participant_b) return 'primary'
  return 'info'
})

const logEvents = computed<GameplayEvent[]>(() => match.value?.gameplay_log?.events ?? [])
const logScores = computed(() => {
  const s = match.value?.gameplay_log?.scores
  return { defender: s?.defender ?? null, attacker: s?.attacker ?? null }
})
const logWinner = computed(() => match.value?.gameplay_log?.winner ?? null)
const logImportedAt = computed(() => match.value?.gameplay_log?.imported_at ?? null)

const logWinnerText = computed(() => {
  switch (logWinner.value) {
    case 'defender':
      return '守护者'
    case 'attacker':
      return '掠夺者'
    case 'draw':
      return '平局'
    default:
      return '未判定'
  }
})

const logWinnerTagType = computed(() => {
  switch (logWinner.value) {
    case 'defender':
      return 'primary'
    case 'attacker':
      return 'danger'
    case 'draw':
      return 'warning'
    default:
      return 'info'
  }
})

function eventTypeClass(type: string): string {
  switch (type) {
    case 'l1':
    case 'victory':
      return 'gold'
    case 'encircle':
      return 'blue'
    case 'system':
      return 'muted'
    default:
      return 'default'
  }
}

function formatScore(score: number | null | undefined): string {
  if (score === null || score === undefined) return '-'
  return String(score)
}

function formatTime(iso: string | null): string {
  if (!iso) return '-'
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return iso
  return d.toLocaleString()
}

function goBack(): void {
  const cid = match.value?.competition_id
  if (cid) {
    router.push(`/competitions/${cid}`)
  } else {
    router.back()
  }
}

function connectWs(): void {
  const proto = location.protocol === 'https:' ? 'wss' : 'ws'
  ws = new WebSocket(`${proto}://${location.host}/ws/matches/${matchId.value}`)

  ws.onmessage = () => {
    // 简化帧：match_started / score_update / no_session 都只需刷新对局数据。
    loadMatch()
  }

  ws.onclose = (event) => {
    if (unmounted) return
    if (event.code === 1008) {
      ElMessage.info('对局已关闭')
      return
    }
    if (reconnectTimer) clearTimeout(reconnectTimer)
    reconnectTimer = setTimeout(() => {
      if (unmounted) return
      if (!ws || ws.readyState === WebSocket.CLOSED) connectWs()
    }, 3000)
  }
}

async function loadMatch(): Promise<void> {
  try {
    const { data: detail } = await http.get<MatchDetailResp>(`/matches/${matchId.value}`)
    match.value = detail.match
  } catch {
    ElMessage.error('加载对局信息失败')
  }
}

async function onRandomizeSides(): Promise<void> {
  randomizingSides.value = true
  try {
    await http.post(`/matches/${matchId.value}/randomize-sides`, {})
    ElMessage.success('已随机选边（掠夺者/守护者可能已对调）')
    await loadMatch()
  } catch (e: unknown) {
    const detail = (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail
    ElMessage.error(detail || '随机选边失败')
  } finally {
    randomizingSides.value = false
  }
}

async function onStartMatch(): Promise<void> {
  starting.value = true
  try {
    await http.post(`/matches/${matchId.value}/start`, {})
    ElMessage.success('对局已开始')
    await loadMatch()
  } catch (e: unknown) {
    const detail = (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail
    ElMessage.error(detail || '开赛失败')
  } finally {
    starting.value = false
  }
}

function openJudgePanel(): void {
  const r = match.value?.result
  resultForm.score_a = r?.score_a ?? 0
  resultForm.score_b = r?.score_b ?? 0
  if (r?.is_draw) {
    resultForm.winner = 'draw'
  } else if (r?.winner === match.value?.participant_a) {
    resultForm.winner = 'raider'
  } else if (r?.winner === match.value?.participant_b) {
    resultForm.winner = 'guardian'
  } else {
    resultForm.winner = 'raider'
  }
  judgeOpen.value = true
}

async function onSaveResult(): Promise<void> {
  submittingResult.value = true
  try {
    const isDraw = resultForm.winner === 'draw'
    const winner = isDraw
      ? null
      : resultForm.winner === 'raider'
        ? match.value?.participant_a ?? null
        : match.value?.participant_b ?? null
    await http.post(`/matches/${matchId.value}/result`, {
      winner,
      is_draw: isDraw,
      score_a: resultForm.score_a,
      score_b: resultForm.score_b,
      lock: true,
    })
    ElMessage.success('结果已保存并锁定，无法再更改')
    judgeOpen.value = false
    await loadMatch()
  } catch (e: unknown) {
    const detail = (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail
    ElMessage.error(detail || '保存结果失败')
  } finally {
    submittingResult.value = false
  }
}

function onFileChange(event: Event): void {
  const input = event.target as HTMLInputElement
  selectedFile.value = input.files?.[0] ?? null
  importSuccess.value = false
}

async function onImportLog(): Promise<void> {
  if (!selectedFile.value) {
    ElMessage.warning('请先选择日志文件')
    return
  }
  importing.value = true
  try {
    const form = new FormData()
    form.append('file', selectedFile.value)
    const url = syncScores.value
      ? `/matches/${matchId.value}/gameplay-log?sync=true`
      : `/matches/${matchId.value}/gameplay-log`
    await http.post(url, form)
    ElMessage.success('玩法日志导入成功')
    importSuccess.value = true
    selectedFile.value = null
    if (fileInput.value) fileInput.value.value = ''
    await loadMatch()
    // 同步判定后把解析结果带入表单，裁判可微调。
    if (syncScores.value) {
      const log = match.value?.gameplay_log
      if (log) {
        resultForm.score_a = log.scores.attacker ?? 0
        resultForm.score_b = log.scores.defender ?? 0
        if (log.winner === 'defender') resultForm.winner = 'guardian'
        else if (log.winner === 'attacker') resultForm.winner = 'raider'
        else if (log.winner === 'draw') resultForm.winner = 'draw'
      }
    }
  } catch (e: unknown) {
    const detail = (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail
    ElMessage.error(detail || '导入玩法日志失败')
  } finally {
    importing.value = false
  }
}

onMounted(async () => {
  await auth.fetchMe()
  await loadMatch()
  connectWs()
})

onBeforeUnmount(() => {
  unmounted = true
  if (reconnectTimer) {
    clearTimeout(reconnectTimer)
    reconnectTimer = null
  }
  if (ws) {
    ws.onclose = null
    ws.close()
    ws = null
  }
})
</script>

<style scoped>
.match-play {
  max-width: 1100px;
  margin: 0 auto;
  padding: 0 16px;
}
.match-play__header {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 20px;
}
.match-play__header h1 {
  margin: 0;
  font-size: 22px;
}
.match-play__state {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 24px;
  padding: 24px 0;
}
.match-play__teams {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 24px;
  width: 100%;
  flex-wrap: wrap;
}
.match-play__team {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
  padding: 24px 32px;
  border-radius: 12px;
  min-width: 200px;
}
.match-play__team--red {
  background: #fef0f0;
  border: 1px solid #f56c6c;
}
.match-play__team--blue {
  background: #ecf5ff;
  border: 1px solid #409eff;
}
.match-play__team-label {
  font-size: 14px;
  font-weight: 600;
  letter-spacing: 2px;
}
.match-play__team--red .match-play__team-label {
  color: #f56c6c;
}
.match-play__team--blue .match-play__team-label {
  color: #409eff;
}
.match-play__team-name {
  font-size: 20px;
  font-weight: 700;
  color: #303133;
  text-align: center;
}
.match-play__vs {
  font-size: 24px;
  font-weight: 800;
  color: #909399;
}
.match-play__action {
  display: flex;
  gap: 12px;
}
.match-play__notice {
  width: 100%;
  max-width: 480px;
}
.match-play__live {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 8px 20px;
  border-radius: 999px;
  background: #f0f9eb;
  border: 1px solid #67c23a;
}
.match-play__live-dot {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  background: #67c23a;
  animation: pulse 1.2s ease-in-out infinite;
}
.match-play__live-text {
  font-size: 16px;
  font-weight: 700;
  color: #67c23a;
}
@keyframes pulse {
  0%,
  100% {
    opacity: 1;
    transform: scale(1);
  }
  50% {
    opacity: 0.4;
    transform: scale(0.8);
  }
}
.match-play__section {
  width: 100%;
  max-width: 720px;
  margin: 0 auto 24px;
  padding: 20px;
  border: 1px solid #ebeef5;
  border-radius: 12px;
  background: #fff;
}
.match-play__section-title {
  margin: 0 0 16px;
  font-size: 16px;
  font-weight: 700;
  color: #303133;
}
.match-play__result {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 12px;
}
.match-play__result-line {
  display: flex;
  align-items: center;
  gap: 16px;
  font-size: 20px;
  font-weight: 700;
}
.match-play__result-team--red {
  color: #f56c6c;
}
.match-play__result-team--blue {
  color: #409eff;
}
.match-play__result-score {
  color: #303133;
  font-size: 24px;
}
.match-play__result-winner {
  display: flex;
  align-items: center;
  gap: 8px;
}
.match-play__import {
  display: flex;
  align-items: center;
  gap: 16px;
  flex-wrap: wrap;
  margin-bottom: 16px;
}
.match-play__file-input {
  max-width: 260px;
}
.match-play__file-name {
  font-size: 13px;
  color: #606266;
}
.match-play__form {
  margin-top: 8px;
  max-width: 420px;
}
.match-play__lock-hint {
  margin-top: 8px;
  font-size: 12px;
  color: #909399;
  text-align: center;
}
.match-play__lock-badge {
  margin-top: 12px;
  padding: 8px 16px;
  border-radius: 8px;
  background: #f0f9eb;
  color: #67c23a;
  font-size: 13px;
}
.match-play__log-summary {
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin-bottom: 16px;
  padding: 12px 16px;
  background: #f8f9fb;
  border-radius: 8px;
  font-size: 14px;
  color: #303133;
}
.match-play__log-scores {
  font-weight: 600;
}
.match-play__log-winner {
  display: flex;
  align-items: center;
  gap: 8px;
}
.match-play__log-time {
  font-size: 12px;
  color: #909399;
}
.match-play__timeline {
  max-height: 360px;
  overflow-y: auto;
  border: 1px solid #ebeef5;
  border-radius: 8px;
  padding: 8px 0;
}
.match-play__event {
  display: flex;
  gap: 12px;
  padding: 8px 16px;
  font-size: 14px;
  border-bottom: 1px solid #f5f7fa;
}
.match-play__event:last-child {
  border-bottom: none;
}
.match-play__event-time {
  flex-shrink: 0;
  font-family: monospace;
  color: #909399;
  min-width: 48px;
}
.match-play__event-text {
  color: #303133;
}
.match-play__event--gold .match-play__event-text {
  color: #b8860b;
  font-weight: 600;
}
.match-play__event--blue .match-play__event-text {
  color: #409eff;
}
.match-play__event--muted .match-play__event-text {
  color: #909399;
}
.match-play__empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 16px;
  padding: 48px 0;
}
</style>
