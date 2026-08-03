<template>
  <div class="tri-board">
    <!-- Scores + timer header -->
    <div class="tri-header">
      <div class="tri-score tri-score--defender">
        <span class="tri-score__team">守护者</span>
        <span class="tri-score__value">{{ formatScore(scores.defender) }}</span>
      </div>
      <div class="tri-timer">
        <el-tag :type="timerType" effect="dark" size="large">
          {{ formatTime(elapsed) }} / {{ formatTime(timeLimit) }}
        </el-tag>
        <div v-if="encirclementActive" class="tri-encircle-badge">包围中</div>
      </div>
      <div class="tri-score tri-score--attacker">
        <span class="tri-score__team">掠夺者</span>
        <span class="tri-score__value">{{ formatScore(scores.attacker) }}</span>
      </div>
    </div>

    <!-- Board -->
    <div class="tri-board__stage">
      <div
        v-for="cell in cells"
        :key="cell.id"
        class="tri-cell"
        :class="cellClass(cell)"
        :style="cellStyle(cell)"
        :title="cellTitle(cell)"
        @click="onCellClick(cell)"
      >
        <span class="tri-cell__label">{{ cellLabel(cell) }}</span>
        <span v-if="!cell.is_energy" class="tri-cell__score">{{ cell.total_score }}</span>
      </div>

      <!-- Game over overlay -->
      <div v-if="gameOver" class="tri-overlay">
        <div class="tri-overlay__card">
          <h2 class="tri-overlay__title">对局结束</h2>
          <p class="tri-overlay__winner">
            {{ winnerText }}
          </p>
          <p class="tri-overlay__score">
            守护者 {{ formatScore(scores.defender) }} : {{ formatScore(scores.attacker) }} 掠夺者
          </p>
        </div>
      </div>
    </div>

    <!-- Events log -->
    <div class="tri-events">
      <h3 class="tri-events__title">对局动态</h3>
      <ul class="tri-events__list">
        <li v-for="(ev, i) in events" :key="i" class="tri-events__item">
          <span class="tri-events__time">{{ ev.time }}</span>
          <span class="tri-events__text">{{ ev.text }}</span>
        </li>
        <li v-if="events.length === 0" class="tri-events__empty">暂无动态</li>
      </ul>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'

export interface TriangleCell {
  id: number
  layer: number
  is_energy: boolean
  owner: 'defender' | 'attacker' | null
  activated: boolean
  diff_score: number
  difficulty_label: string
  task_name: string
  task_bonus: number
  total_score: number
  energy_bonus: number
}

export interface TriangleEvent {
  time: string
  text: string
  type: string
}

export interface TriangleState {
  board: TriangleCell[]
  scores: { defender: number; attacker: number }
  encircled: number[]
  encirclement_active: boolean
  l1: { holder: string | null; high_score: number | null; high_tp: number | null }
  elapsed: number
  time_limit: number
  events: TriangleEvent[]
  game_over: boolean
  winner: string | null
  win_type: string | null
}

const props = defineProps<{
  state: TriangleState | null
  selectable?: boolean
}>()

const emit = defineEmits<{
  (e: 'select', cell: TriangleCell): void
}>()

const cells = computed<TriangleCell[]>(() => props.state?.board ?? [])
const scores = computed(() => props.state?.scores ?? { defender: 0, attacker: 0 })
const elapsed = computed(() => props.state?.elapsed ?? 0)
const timeLimit = computed(() => props.state?.time_limit ?? 0)
const encirclementActive = computed(() => props.state?.encirclement_active ?? false)
const events = computed(() => props.state?.events ?? [])
const gameOver = computed(() => props.state?.game_over ?? false)
const winner = computed(() => props.state?.winner ?? null)
const winType = computed(() => props.state?.win_type ?? null)

const encircledSet = computed(() => new Set(props.state?.encircled ?? []))

// Mirror backend board.cell_positions: 3-layer triangle + 6 energy cells.
function cellPosition(cell: TriangleCell): { x: number; y: number } {
  const width = 640
  const height = 560
  const marginX = width * 0.08
  const marginY = height * 0.06
  const usableW = width - 2 * marginX
  const usableH = height - 2 * marginY
  const dx = usableW / 6.0
  const dy = usableH / 7.0
  const cx = width / 2.0

  if (cell.is_energy) {
    const i = cell.id - 21
    return { x: cx + (i - 2.5) * dx, y: marginY + 6 * dy }
  }
  const layer = cell.layer
  const start = (layer * (layer - 1)) / 2
  const idx = cell.id - start
  return {
    x: cx + (idx - (layer - 1) / 2.0) * dx,
    y: marginY + (layer - 1) * dy,
  }
}

function cellStyle(cell: TriangleCell): Record<string, string> {
  const { x, y } = cellPosition(cell)
  return {
    left: `${x}px`,
    top: `${y}px`,
  }
}

function cellClass(cell: TriangleCell): Record<string, boolean> {
  return {
    'tri-cell--defender': cell.owner === 'defender',
    'tri-cell--attacker': cell.owner === 'attacker',
    'tri-cell--neutral': cell.owner === null,
    'tri-cell--energy': cell.is_energy,
    'tri-cell--activated': cell.activated,
    'tri-cell--encircled': encircledSet.value.has(cell.id),
    'tri-cell--selectable': !!props.selectable,
  }
}

function cellLabel(cell: TriangleCell): string {
  if (cell.is_energy) return '⚡'
  if (cell.id === 0) return 'L1'
  return `L${cell.layer}`
}

function cellTitle(cell: TriangleCell): string {
  if (cell.is_energy) return '能量格'
  const owner = cell.owner === 'defender' ? '守护者' : cell.owner === 'attacker' ? '掠夺者' : '中立'
  const parts = [
    `L${cell.layer}格`,
    `难度: ${cell.difficulty_label || '-'}`,
    `任务: ${cell.task_name || '-'}`,
    `分值: ${cell.total_score}`,
    `占领: ${owner}`,
  ]
  if (cell.activated) parts.push('已激活')
  if (encircledSet.value.has(cell.id)) parts.push('包围中')
  return parts.join(' | ')
}

function onCellClick(cell: TriangleCell): void {
  if (props.selectable) emit('select', cell)
}

function formatScore(v: number): string {
  return Number.isInteger(v) ? String(v) : v.toFixed(1)
}

function formatTime(minutes: number): string {
  const m = Math.floor(minutes)
  const s = Math.round((minutes - m) * 60)
  return `${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`
}

const timerType = computed(() => {
  if (gameOver.value) return 'info'
  if (timeLimit.value > 0 && elapsed.value >= timeLimit.value * 0.9) return 'danger'
  if (timeLimit.value > 0 && elapsed.value >= timeLimit.value * 0.7) return 'warning'
  return 'success'
})

const winnerText = computed(() => {
  if (!gameOver.value) return ''
  if (winner.value === 'draw') return '平局'
  const team = winner.value === 'defender' ? '守护者' : '掠夺者'
  const type = winType.value === 'top' ? '（顶端直胜）' : winType.value === 'timeout' ? '（时间到）' : ''
  return `${team}获胜${type}`
})
</script>

<style scoped>
.tri-board {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.tri-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
}

.tri-score {
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 8px 20px;
  border-radius: 8px;
  min-width: 120px;
}
.tri-score--defender {
  background: #ecf5ff;
  border: 1px solid #a0cfff;
}
.tri-score--attacker {
  background: #fef0f0;
  border: 1px solid #fbc4c4;
}
.tri-score__team {
  font-size: 13px;
  color: #606266;
}
.tri-score__value {
  font-size: 24px;
  font-weight: 700;
}
.tri-score--defender .tri-score__value {
  color: #409eff;
}
.tri-score--attacker .tri-score__value {
  color: #f56c6c;
}

.tri-timer {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 4px;
}
.tri-encircle-badge {
  font-size: 12px;
  color: #e6a23c;
  font-weight: 600;
}

.tri-board__stage {
  position: relative;
  width: 640px;
  height: 560px;
  margin: 0 auto;
  background: linear-gradient(180deg, #f7f9fc 0%, #eef1f6 100%);
  border: 1px solid #e4e7ed;
  border-radius: 12px;
}

.tri-cell {
  position: absolute;
  width: 56px;
  height: 56px;
  transform: translate(-50%, -50%);
  border-radius: 8px;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  border: 2px solid #c0c4cc;
  background: #ffffff;
  cursor: default;
  transition: transform 0.15s ease, box-shadow 0.15s ease;
  user-select: none;
}
.tri-cell--selectable {
  cursor: pointer;
}
.tri-cell--selectable:hover {
  transform: translate(-50%, -50%) scale(1.08);
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
}
.tri-cell--defender {
  background: #409eff;
  border-color: #337ecc;
  color: #fff;
}
.tri-cell--attacker {
  background: #f56c6c;
  border-color: #d9534f;
  color: #fff;
}
.tri-cell--energy {
  background: #fdf6ec;
  border-color: #e6a23c;
  border-style: dashed;
}
.tri-cell--activated {
  box-shadow: 0 0 0 3px rgba(230, 162, 60, 0.6);
}
.tri-cell--encircled {
  outline: 3px solid #e6a23c;
  outline-offset: 2px;
}
.tri-cell__label {
  font-size: 12px;
  font-weight: 600;
  line-height: 1.2;
}
.tri-cell__score {
  font-size: 11px;
  opacity: 0.9;
}

.tri-overlay {
  position: absolute;
  inset: 0;
  background: rgba(255, 255, 255, 0.85);
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 12px;
  z-index: 10;
}
.tri-overlay__card {
  text-align: center;
  padding: 24px 40px;
  background: #fff;
  border-radius: 12px;
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.15);
}
.tri-overlay__title {
  margin: 0 0 8px;
  font-size: 22px;
}
.tri-overlay__winner {
  font-size: 18px;
  font-weight: 700;
  color: #409eff;
  margin: 0 0 8px;
}
.tri-overlay__score {
  margin: 0;
  color: #606266;
}

.tri-events {
  border: 1px solid #e4e7ed;
  border-radius: 8px;
  padding: 12px 16px;
  max-height: 220px;
  overflow-y: auto;
}
.tri-events__title {
  margin: 0 0 8px;
  font-size: 14px;
  color: #303133;
}
.tri-events__list {
  list-style: none;
  margin: 0;
  padding: 0;
}
.tri-events__item {
  display: flex;
  gap: 8px;
  font-size: 13px;
  padding: 2px 0;
}
.tri-events__time {
  color: #909399;
  flex-shrink: 0;
}
.tri-events__text {
  color: #303133;
}
.tri-events__empty {
  color: #909399;
  font-size: 13px;
}
</style>
