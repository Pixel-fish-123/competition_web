<template>
  <div class="schedule-chart">
    <!-- 空赛程 -->
    <div v-if="totalMatches === 0" class="schedule-chart__empty">
      <el-empty description="暂无赛程" />
    </div>

    <!-- 单败淘汰：树状签表 -->
    <div v-else-if="isSingleElim" class="schedule-chart__bracket">
      <div
        class="bracket"
        :style="{ '--bracket-h': bracketHeight + 'px', '--match-h': MATCH_H + 'px' }"
      >
        <div
          v-for="round in bracketRounds"
          :key="round.round_id"
          class="bracket__round"
        >
          <div class="bracket__round-title">
            {{ roundName(round.round_id, bracketRounds.length) }}
          </div>
          <div class="bracket__round-matches">
            <div
              v-for="m in round.matches"
              :key="m.id"
              class="bracket__match"
            >
              <div
                v-if="round.connectorSpan > 0"
                class="bracket__connector"
                :style="{ '--span': round.connectorSpan + 'px' }"
                aria-hidden="true"
              ></div>
              <div
                class="bracket__card"
                :class="cardStatusClass(m.status)"
                @click="emit('select', m)"
              >
                <div class="bracket__slot" :class="slotClass(m, 'a')">
                  <span class="bracket__name">{{ nameOf(m, 'a') }}</span>
                  <span v-if="isBye(m)" class="bracket__bye">轮空</span>
                  <span v-else class="bracket__score">{{ scoreOf(m, 'a') }}</span>
                </div>
                <div class="bracket__slot" :class="slotClass(m, 'b')">
                  <span class="bracket__name">{{ nameOf(m, 'b') }}</span>
                  <span v-if="isBye(m)" class="bracket__bye">—</span>
                  <span v-else class="bracket__score">{{ scoreOf(m, 'b') }}</span>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- 季军赛侧分支 -->
      <div v-if="thirdPlaceRound" class="bracket__third">
        <div class="bracket__third-title">季军赛</div>
        <div class="bracket__match">
          <div class="bracket__connector bracket__connector--third" aria-hidden="true"></div>
          <div
            class="bracket__card"
            :class="cardStatusClass(thirdPlaceRound.matches[0].status)"
            @click="emit('select', thirdPlaceRound.matches[0])"
          >
            <div class="bracket__slot" :class="slotClass(thirdPlaceRound.matches[0], 'a')">
              <span class="bracket__name">{{ nameOf(thirdPlaceRound.matches[0], 'a') }}</span>
              <span class="bracket__score">{{ scoreOf(thirdPlaceRound.matches[0], 'a') }}</span>
            </div>
            <div class="bracket__slot" :class="slotClass(thirdPlaceRound.matches[0], 'b')">
              <span class="bracket__name">{{ nameOf(thirdPlaceRound.matches[0], 'b') }}</span>
              <span class="bracket__score">{{ scoreOf(thirdPlaceRound.matches[0], 'b') }}</span>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- 循环赛 / 瑞士轮：轮次对阵矩阵 -->
    <div v-else-if="isRoundRobin || isSwiss" class="schedule-chart__rounds">
      <div class="rounds-table">
        <div
          v-for="round in rounds"
          :key="round.round_id"
          class="rounds-table__col"
        >
          <div class="rounds-table__header">第 {{ round.round_id }} 轮</div>
          <div
            v-for="m in round.matches"
            :key="m.id"
            class="rounds-table__match"
            @click="emit('select', m)"
          >
            <div class="rounds-table__pair">
              <span class="rounds-table__name" :class="{ 'is-winner': isWinner(m, 'a') }">
                {{ nameOf(m, 'a') }}
              </span>
              <span class="rounds-table__score">{{ middleText(m) }}</span>
              <span class="rounds-table__name" :class="{ 'is-winner': isWinner(m, 'b') }">
                {{ nameOf(m, 'b') }}
              </span>
            </div>
            <div class="rounds-table__foot">
              <el-tag size="small" :type="statusType(m.status)">
                {{ statusLabel(m.status) }}
              </el-tag>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- 未知赛制：兜底表格 -->
    <div v-else class="schedule-chart__fallback">
      <el-table :data="flatMatches" size="small" border>
        <el-table-column label="轮次" width="90">
          <template #default="{ row }">第 {{ row.round_id }} 轮</template>
        </el-table-column>
        <el-table-column label="对阵">
          <template #default="{ row }">
            <span class="fallback__pair">
              <span :class="{ 'is-winner': isWinner(row, 'a') }">{{ nameOf(row, 'a') }}</span>
              <span class="fallback__vs">VS</span>
              <span :class="{ 'is-winner': isWinner(row, 'b') }">{{ nameOf(row, 'b') }}</span>
            </span>
          </template>
        </el-table-column>
        <el-table-column label="状态" width="110">
          <template #default="{ row }">
            <el-tag size="small" :type="statusType(row.status)">
              {{ statusLabel(row.status) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="结果" width="160">
          <template #default="{ row }">{{ resultText(row) }}</template>
        </el-table-column>
      </el-table>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'

interface MatchInfo {
  id: number
  round_id: number
  participant_a: number | null
  participant_b: number | null
  participant_a_name?: string | null
  participant_b_name?: string | null
  status: string
  result: Record<string, any> | null
  result_type?: string | null
}

interface RoundGroup {
  round_id: number
  matches: MatchInfo[]
}

interface BracketRound extends RoundGroup {
  connectorSpan: number
}

const props = defineProps<{
  rounds: RoundGroup[]
  format: string
}>()

const emit = defineEmits<{
  (e: 'select', match: MatchInfo): void
}>()

// 签表几何常量：卡片高度 + 轮内间距 = 单元格高度。
const MATCH_H = 76
const CELL = 104

const isSingleElim = computed(() => props.format === 'single_elim')
const isRoundRobin = computed(() => props.format === 'round_robin')
const isSwiss = computed(() => props.format === 'swiss')

const totalMatches = computed(() =>
  props.rounds.reduce((sum, r) => sum + r.matches.length, 0)
)

const sortedRounds = computed(() =>
  [...props.rounds].sort((a, b) => a.round_id - b.round_id)
)

// 主签表轮次（冠军路径）与季军赛侧分支分离。
// 季军赛：最后一轮单场且其前一轮也是单场（即决赛）时，最后一轮为季军赛。
const mainRounds = computed<RoundGroup[]>(() => {
  const s = sortedRounds.value
  if (s.length === 0) return []
  const last = s[s.length - 1]
  let end = s.length
  if (
    last.matches.length === 1 &&
    s.length >= 2 &&
    s[s.length - 2].matches.length === 1
  ) {
    end = s.length - 1
  }
  return s.slice(0, end)
})

const thirdPlaceRound = computed<RoundGroup | null>(() => {
  const s = sortedRounds.value
  const main = mainRounds.value
  if (main.length === s.length) return null
  return s[main.length] ?? null
})

const round1Count = computed(() =>
  mainRounds.value.length > 0 ? mainRounds.value[0].matches.length : 0
)

const bracketHeight = computed(() => round1Count.value * CELL)

// 为每轮计算连接线纵向跨度：上一轮匹配数决定该轮每个节点的垂直间距。
const bracketRounds = computed<BracketRound[]>(() => {
  const main = mainRounds.value
  const h = bracketHeight.value
  return main.map((r, i) => {
    let span = 0
    if (i > 0 && main[i - 1].matches.length > 0) {
      span = h / main[i - 1].matches.length
    }
    return { ...r, connectorSpan: span }
  })
})

const flatMatches = computed<MatchInfo[]>(() =>
  sortedRounds.value.flatMap((r) => r.matches)
)

// 轮次命名：第一轮固定为「第一轮」，其后按距决赛的远近命名。
function roundName(roundIndex: number, totalRounds: number): string {
  if (roundIndex === 1) return '第一轮'
  const fromEnd = totalRounds - roundIndex + 1
  if (fromEnd === 1) return '决赛'
  if (fromEnd === 2) return '半决赛'
  if (fromEnd === 3) return '八强赛'
  if (fromEnd === 4) return '十六强赛'
  return `第 ${roundIndex} 轮`
}

function isBye(m: MatchInfo): boolean {
  // 轮空：单败淘汰中 participant_b 为空（引擎自动晋级 participant_a）。
  return m.participant_b === null
}

function nameOf(m: MatchInfo, side: 'a' | 'b'): string {
  const explicit = side === 'a' ? m.participant_a_name : m.participant_b_name
  if (explicit) return explicit
  const id = side === 'a' ? m.participant_a : m.participant_b
  if (id === null) return '待定'
  return `参赛者#${id}`
}

function scoreOf(m: MatchInfo, side: 'a' | 'b'): string {
  if (!m.result) return ''
  const score = side === 'a' ? m.result.score_a : m.result.score_b
  if (score === null || score === undefined) return ''
  return String(score)
}

function isWinner(m: MatchInfo, side: 'a' | 'b'): boolean {
  if (!m.result) return false
  const winner = m.result.winner
  if (winner === null || winner === undefined) return false
  const id = side === 'a' ? m.participant_a : m.participant_b
  return id !== null && Number(winner) === id
}

function slotClass(m: MatchInfo, side: 'a' | 'b'): string {
  const classes = ['bracket__slot']
  if (isBye(m)) classes.push('bracket__slot--bye')
  if (isWinner(m, side)) classes.push('bracket__slot--winner')
  return classes.join(' ')
}

function middleText(m: MatchInfo): string {
  if (!m.result) return 'VS'
  const a = m.result.score_a
  const b = m.result.score_b
  if (a === null || a === undefined || b === null || b === undefined) return 'VS'
  return `${a} : ${b}`
}

function resultText(m: MatchInfo): string {
  if (!m.result) return '—'
  const winner = m.result.winner
  if (winner === null || winner === undefined) return '平局'
  const w = Number(winner)
  const side = w === m.participant_a ? 'a' : w === m.participant_b ? 'b' : null
  return `胜者：${side ? nameOf(m, side) : `参赛者#${w}`}`
}

function statusLabel(s: string): string {
  if (s === 'in_progress') return '进行中'
  if (s === 'finished') return '已结束'
  return '待开始'
}

function statusType(s: string): 'success' | 'info' | 'warning' {
  if (s === 'in_progress') return 'success'
  if (s === 'finished') return 'info'
  return 'warning'
}

function cardStatusClass(s: string): string {
  if (s === 'in_progress') return 'bracket__card--progress'
  if (s === 'finished') return 'bracket__card--finished'
  return 'bracket__card--pending'
}
</script>

<style scoped>
.schedule-chart__empty {
  padding: 8px 0;
}

/* ---------- 单败淘汰：树状签表 ---------- */
.schedule-chart__bracket {
  overflow-x: auto;
  padding-bottom: 8px;
}
.bracket {
  display: flex;
  gap: 24px;
  min-width: max-content;
  align-items: flex-start;
}
.bracket__round {
  display: flex;
  flex-direction: column;
  min-width: 180px;
}
.bracket__round-title {
  font-size: 13px;
  font-weight: 600;
  color: #606266;
  text-align: center;
  white-space: nowrap;
  padding: 4px 0 10px;
}
.bracket__round-matches {
  display: flex;
  flex-direction: column;
  justify-content: space-around;
  height: var(--bracket-h);
}
.bracket__match {
  position: relative;
}

/* 连接线：每张卡片左侧的 ┐ └ ┘ 肘形线，把上一轮一对匹配汇入本轮 */
.bracket__connector {
  position: absolute;
  right: 100%;
  top: calc(-1 * (var(--span) - var(--match-h)) / 2);
  height: var(--span);
  width: 24px;
  pointer-events: none;
}
.bracket__connector::before {
  /* 轮界处的竖线：从上一轮上方匹配中心延伸到下方匹配中心 */
  content: '';
  position: absolute;
  left: 0;
  top: 0;
  bottom: 0;
  border-left: 2px solid #c0c4cc;
}
.bracket__connector::after {
  /* 汇入本轮的横线 */
  content: '';
  position: absolute;
  left: 0;
  right: 0;
  top: 50%;
  height: 2px;
  transform: translateY(-50%);
  background: #c0c4cc;
}

.bracket__card {
  width: 180px;
  height: var(--match-h);
  border: 1px solid #e4e7ed;
  border-left-width: 3px;
  border-radius: 6px;
  background: #fff;
  cursor: pointer;
  display: flex;
  flex-direction: column;
  justify-content: center;
  padding: 0 10px;
  box-shadow: 0 1px 2px rgba(0, 0, 0, 0.04);
  transition: box-shadow 0.2s, transform 0.2s, border-color 0.2s;
}
.bracket__card:hover {
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.1);
  transform: translateY(-1px);
  border-color: #c0c4cc;
}
.bracket__card--pending {
  border-left-color: #e6a23c;
}
.bracket__card--progress {
  border-left-color: #409eff;
}
.bracket__card--finished {
  border-left-color: #67c23a;
}
.bracket__slot {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  height: 50%;
  padding: 0 2px;
}
.bracket__slot--bye {
  opacity: 0.8;
}
.bracket__slot--winner .bracket__name {
  font-weight: 700;
  color: #67c23a;
}
.bracket__name {
  flex: 1;
  font-size: 13px;
  font-weight: 600;
  color: #303133;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.bracket__score {
  font-size: 12px;
  font-weight: 600;
  color: #909399;
  flex-shrink: 0;
}
.bracket__bye {
  font-size: 11px;
  color: #e6a23c;
  flex-shrink: 0;
}

/* 季军赛侧分支 */
.bracket__third {
  margin-top: 28px;
  display: flex;
  align-items: center;
  gap: 12px;
}
.bracket__third-title {
  font-size: 13px;
  font-weight: 600;
  color: #606266;
  white-space: nowrap;
}
.bracket__connector--third {
  position: absolute;
  right: 100%;
  top: 50%;
  width: 24px;
  height: 2px;
  background: repeating-linear-gradient(90deg, #c0c4cc 0 4px, transparent 4px 8px);
}
.bracket__connector--third::before,
.bracket__connector--third::after {
  display: none;
}

/* ---------- 循环赛 / 瑞士轮：轮次对阵矩阵 ---------- */
.schedule-chart__rounds {
  overflow-x: auto;
  padding-bottom: 8px;
}
.rounds-table {
  display: flex;
  gap: 16px;
  min-width: max-content;
}
.rounds-table__col {
  flex: 0 0 auto;
  width: 230px;
  border: 1px solid #ebeef5;
  border-radius: 8px;
  overflow: hidden;
  background: #fff;
}
.rounds-table__header {
  padding: 10px 12px;
  font-weight: 600;
  font-size: 14px;
  color: #303133;
  background: #f5f7fa;
  border-bottom: 1px solid #ebeef5;
  text-align: center;
}
.rounds-table__match {
  padding: 10px 12px;
  border-bottom: 1px solid #f0f2f5;
  cursor: pointer;
  transition: background-color 0.2s;
}
.rounds-table__match:last-child {
  border-bottom: none;
}
.rounds-table__match:hover {
  background-color: #f5f7fa;
}
.rounds-table__pair {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}
.rounds-table__name {
  flex: 1;
  font-size: 13px;
  color: #303133;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.rounds-table__name.is-winner {
  font-weight: 700;
  color: #67c23a;
}
.rounds-table__score {
  font-size: 13px;
  font-weight: 600;
  color: #606266;
  flex-shrink: 0;
}
.rounds-table__foot {
  margin-top: 6px;
  display: flex;
  justify-content: flex-end;
}

/* ---------- 未知赛制：兜底表格 ---------- */
.schedule-chart__fallback {
  overflow-x: auto;
}
.fallback__pair {
  display: inline-flex;
  align-items: center;
  gap: 8px;
}
.fallback__pair .is-winner {
  font-weight: 700;
  color: #67c23a;
}
.fallback__vs {
  color: #c0c4cc;
  font-size: 12px;
}
</style>
