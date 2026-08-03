<template>
  <div class="match-play">
    <div class="match-play__header">
      <h1>对局 #{{ matchId }}</h1>
      <el-tag v-if="match" :type="matchStatusType" effect="dark">
        {{ matchStatusText }}
      </el-tag>
    </div>

    <div v-if="match" class="match-play__players">{{ playersText }}</div>

    <el-alert
      v-if="!isRefereeOrAdmin"
      type="info"
      :closable="false"
      title="选手只读模式：你只能查看对局，无法操作棋盘。"
      class="match-play__notice"
    />

    <div v-if="noSession" class="match-play__empty">
      <el-empty description="对局尚未开始" />
      <el-button
        v-if="isRefereeOrAdmin"
        type="primary"
        :loading="starting"
        @click="onStartMatch"
      >
        开始对局
      </el-button>
    </div>

    <div v-else-if="state" class="match-play__body">
      <div class="match-play__board">
        <TriangleBoard
          :state="state"
          :selectable="isRefereeOrAdmin && !state.game_over"
          @select="onSelectCell"
        />
      </div>

      <div class="match-play__side">
        <TriangleControls
          v-if="isRefereeOrAdmin"
          :selected-cell="selectedCell"
          :game-over="state.game_over"
          @occupy="onOccupy"
          @cancel="onCancel"
          @reoccupy="onReoccupy"
          @set-time="onSetTime"
          @end-game="onEndGame"
        />

        <div v-if="isRefereeOrAdmin && state.game_over" class="match-play__result">
          <el-button type="success" :loading="recording" @click="onRecordResult">
            记录结果
          </el-button>
        </div>
      </div>
    </div>

    <div v-else class="match-play__empty">
      <el-empty description="连接中…" />
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage } from 'element-plus'
import http from '../api/http'
import { useAuthStore } from '../stores/auth'
import { TriangleBoard, TriangleControls } from '../plugins/triangle-occupy'
import type { TriangleCell, TriangleState } from '../plugins/triangle-occupy/TriangleBoard.vue'

interface MatchInfo {
  id: number
  competition_id: number
  round_id: number
  participant_a: number | null
  participant_b: number | null
  participant_a_name: string | null
  participant_b_name: string | null
  status: string
  result: Record<string, unknown> | null
  result_type: string | null
  referee_id: number | null
}

const route = useRoute()
const auth = useAuthStore()

const matchId = computed(() => Number(route.params.mid))

const match = ref<MatchInfo | null>(null)
const state = ref<TriangleState | null>(null)
const noSession = ref(false)
const selectedCell = ref<TriangleCell | null>(null)
const starting = ref(false)
const recording = ref(false)
const sessionId = ref<number | null>(null)

let ws: WebSocket | null = null

const isRefereeOrAdmin = computed(() => auth.isRefereeOrAdmin)

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

const playersText = computed(() => {
  const m = match.value
  if (!m) return ''
  const aAlone = m.participant_a !== null && m.participant_b === null
  const bAlone = m.participant_b !== null && m.participant_a === null
  if (aAlone) return m.participant_a_name || '选手A'
  if (bAlone) return m.participant_b_name || '选手B'
  const aName = m.participant_a_name || '选手A'
  const bName = m.participant_b_name || '选手B'
  return `${aName} VS ${bName}`
})

function connectWs(): void {
  const proto = location.protocol === 'https:' ? 'wss' : 'ws'
  ws = new WebSocket(`${proto}://${location.host}/ws/matches/${matchId.value}`)

  ws.onmessage = (event) => {
    try {
      const frame = JSON.parse(event.data)
      if (frame.type === 'state_update') {
        state.value = frame.state as TriangleState
        sessionId.value = frame.session_id ?? null
        noSession.value = false
      } else if (frame.type === 'no_session') {
        state.value = null
        sessionId.value = null
        noSession.value = true
      } else if (frame.type === 'session_ended') {
        noSession.value = true
        state.value = null
        sessionId.value = null
      }
    } catch {
      // ignore malformed frames
    }
  }

  ws.onclose = () => {
    // Attempt reconnect after a short delay.
    setTimeout(() => {
      if (!ws || ws.readyState === WebSocket.CLOSED) connectWs()
    }, 3000)
  }
}

async function loadMatch(): Promise<void> {
  try {
    const { data } = await http.get<MatchInfo>(`/matches/${matchId.value}`)
    match.value = data
  } catch {
    ElMessage.error('加载对局信息失败')
  }
}

function onSelectCell(cell: TriangleCell): void {
  selectedCell.value = cell
}

async function submitAction(payload: {
  action: string
  cell_id?: number
  score?: number
  tp?: number
  minutes?: number
}): Promise<void> {
  if (!sessionId.value) {
    ElMessage.warning('对局会话尚未建立')
    return
  }
  try {
    await http.post(`/gameplay/triangle_occupy/session/${sessionId.value}/action`, {
      participant_id: 0,
      payload,
    })
  } catch (e: unknown) {
    const detail = (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail
    ElMessage.error(detail || '操作失败')
  }
}

function onOccupy(payload: { cell_id: number; score?: number; tp?: number }): void {
  submitAction({ action: 'occupy', ...payload })
}

function onCancel(cellId: number): void {
  submitAction({ action: 'cancel', cell_id: cellId })
}

function onReoccupy(cellId: number): void {
  submitAction({ action: 'reoccupy', cell_id: cellId })
}

function onSetTime(minutes: number): void {
  submitAction({ action: 'set_time', minutes })
}

async function onEndGame(): Promise<void> {
  if (!sessionId.value) {
    ElMessage.warning('对局会话尚未建立')
    return
  }
  try {
    await http.post(`/gameplay/triangle_occupy/session/${sessionId.value}/end`)
    ElMessage.success('对局已结束')
  } catch (e: unknown) {
    const detail = (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail
    ElMessage.error(detail || '结束对局失败')
  }
}

async function onStartMatch(): Promise<void> {
  starting.value = true
  try {
    await http.post(`/matches/${matchId.value}/start`, {})
    ElMessage.success('对局已开始')
  } catch (e: unknown) {
    const detail = (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail
    ElMessage.error(detail || '开赛失败')
  } finally {
    starting.value = false
  }
}

async function onRecordResult(): Promise<void> {
  if (!state.value) return
  recording.value = true
  try {
    const winner =
      state.value.winner === 'draw'
        ? null
        : state.value.winner === 'defender'
          ? match.value?.participant_a ?? null
          : match.value?.participant_b ?? null
    await http.post(`/matches/${matchId.value}/result`, {
      winner,
      is_draw: state.value.winner === 'draw',
      score_a: state.value.scores.defender,
      score_b: state.value.scores.attacker,
    })
    ElMessage.success('结果已记录')
  } catch (e: unknown) {
    const detail = (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail
    ElMessage.error(detail || '记录结果失败')
  } finally {
    recording.value = false
  }
}

onMounted(async () => {
  await auth.fetchMe()
  await loadMatch()
  connectWs()
})

onBeforeUnmount(() => {
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
}
.match-play__header {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 16px;
}
.match-play__header h1 {
  margin: 0;
  font-size: 22px;
}
.match-play__players {
  text-align: center;
  font-size: 16px;
  font-weight: 600;
  color: #303133;
  padding: 10px 0;
  margin-bottom: 16px;
  border-bottom: 1px solid #ebeef5;
}
.match-play__notice {
  margin-bottom: 16px;
}
.match-play__body {
  display: flex;
  gap: 24px;
  align-items: flex-start;
  flex-wrap: wrap;
}
.match-play__board {
  flex: 1;
  min-width: 640px;
}
.match-play__side {
  width: 320px;
  display: flex;
  flex-direction: column;
  gap: 16px;
}
.match-play__empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 16px;
  padding: 48px 0;
}
.match-play__result {
  text-align: center;
}
</style>
