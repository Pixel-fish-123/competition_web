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
        <component
          :is="boardComp"
          v-if="boardComp"
          :state="state"
          :selectable="isRefereeOrAdmin && !state.game_over"
          @select="onSelectCell"
        />
        <el-alert
          v-else
          type="warning"
          title="该玩法暂未支持前端组件"
          :closable="false"
        />
      </div>

      <div class="match-play__side">
        <div
          v-if="isRefereeOrAdmin && !state.game_over"
          class="match-play__acting"
        >
          <span class="match-play__acting-label">替哪一方操作</span>
          <el-radio-group v-model="actingSide" size="small">
            <el-radio-button value="defender">守护者方</el-radio-button>
            <el-radio-button value="attacker">掠夺者方</el-radio-button>
          </el-radio-group>
        </div>

        <component
          :is="controlsComp"
          v-if="isRefereeOrAdmin && controlsComp"
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
import type { Component } from 'vue'

// 玩法插件组件映射表（todo 6）：按 gameplay_plugin 名解析对局页的棋盘/操作组件。
// 保留静态 import（单玩法映射表足够，不引入动态 import）。
const PLUGIN_COMPONENTS: Record<string, { board: Component; controls: Component | null }> = {
  triangle_occupy: { board: TriangleBoard, controls: TriangleControls },
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
  result: Record<string, unknown> | null
  result_type: string | null
  referee_id: number | null
  gameplay_plugin: string | null
}

// GET /api/matches/{id} 返回嵌套的 MatchDetailOut = {match, session}
// （todo 2 ①：旧代码把整个响应当扁平 MatchInfo 用，participant_a/status 全 undefined）。
interface MatchDetailResp {
  match: MatchInfo
  session: { id: number; state: Record<string, unknown> | null } | null
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
// 裁判替哪一方操作（todo 2 ③）：defender -> participant_a，attacker -> participant_b。
const actingSide = ref<'defender' | 'attacker'>('defender')

let ws: WebSocket | null = null
let reconnectTimer: ReturnType<typeof setTimeout> | null = null
let unmounted = false

const isRefereeOrAdmin = computed(() => auth.isRefereeOrAdmin)

// todo 6：按 gameplay_plugin 名解析玩法组件；未知插件名时 boardComp 为 null，
// 模板渲染降级提示而非白屏。
const pluginComp = computed(() => PLUGIN_COMPONENTS[match.value?.gameplay_plugin ?? ''] ?? null)
const boardComp = computed(() => pluginComp.value?.board ?? null)
const controlsComp = computed(() => pluginComp.value?.controls ?? null)

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
      // WS 帧的 state 是 get_state 的嵌套公开视图 {controller_state: {...},
      // elapsed_minutes, sides, game_over, winner}（plugin.py:185-196），而
      // TriangleState 期望扁平字段。解包：controller_state 提供棋盘字段，
      // 外层 elapsed_minutes 等作为补充（todo 2 ②）。
      const unpack = (raw: any): TriangleState =>
        (raw?.controller_state ? { ...raw.controller_state, ...raw } : raw) as TriangleState
      if (frame.type === 'state_update') {
        state.value = unpack(frame.state)
        sessionId.value = frame.session_id ?? null
        noSession.value = false
      } else if (frame.type === 'no_session') {
        state.value = null
        sessionId.value = null
        noSession.value = true
      } else if (frame.type === 'session_ended') {
        // 会话结束保留最终状态（todo 2 ④）：帧带 state 用之（含 game_over=true），
        // 否则保留旧值 —— 保证"记录结果"按钮（v-if=state.game_over）可见、
        // 棋盘仍显示终局。不清空 state。
        if (frame.state) {
          state.value = unpack(frame.state)
        }
        noSession.value = false
        sessionId.value = null
      }
    } catch {
      // ignore malformed frames
    }
  }

  ws.onclose = (event) => {
    if (unmounted) return
    if (event.code === 1008) {
      // 对局/比赛被删除或无权限：停止无限重连（todo 8 删除 finished 比赛后
      // 不应残留订阅者每 3s 重连一次）。
      ElMessage.info('对局已关闭')
      return
    }
    // Attempt reconnect after a short delay.
    if (reconnectTimer) clearTimeout(reconnectTimer)
    reconnectTimer = setTimeout(() => {
      if (unmounted) return
      if (!ws || ws.readyState === WebSocket.CLOSED) connectWs()
    }, 3000)
  }
}

async function loadMatch(): Promise<void> {
  try {
    // 响应是嵌套 MatchDetailOut={match, session}（todo 2 ①）：解包取 data.match，
    // 会话存在时预填 sessionId。
    const { data: detail } = await http.get<MatchDetailResp>(`/matches/${matchId.value}`)
    match.value = detail.match
    if (detail.session) {
      sessionId.value = detail.session.id
    }
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
  // todo 2 ③：按替操作方推导被操作的参赛单位 id（defender -> participant_a，
  // attacker -> participant_b）。不再硬编码 0 —— 后端 validate_result 对 0
  // 会以 400「非法操作」拒绝。
  const pid =
    actingSide.value === 'defender'
      ? match.value?.participant_a
      : match.value?.participant_b
  if (pid === null || pid === undefined) {
    ElMessage.warning('该侧参赛者未确定，请先开赛')
    return
  }
  try {
    await http.post(`/gameplay/triangle_occupy/session/${sessionId.value}/action`, {
      participant_id: pid,
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
.match-play__acting {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 12px 16px;
  border: 1px solid #e4e7ed;
  border-radius: 8px;
  background: #f8f9fb;
}
.match-play__acting-label {
  font-size: 13px;
  color: #606266;
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
