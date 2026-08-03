<template>
  <div class="schedule-chart">
    <!-- 空赛程 -->
    <div v-if="totalMatches === 0" class="schedule-chart__empty">
      <el-empty description="暂无赛程" />
    </div>

    <!-- 单败淘汰：bracket 签表 -->
    <div v-else-if="isSingleElim" class="schedule-chart__bracket">
      <div class="bracket">
        <div
          v-for="round in bracketRounds"
          :key="round.round_id"
          class="bracket__round"
          :class="{ 'bracket__round--third': round.isThirdPlace }"
        >
          <div class="bracket__round-title">
            {{ round.isThirdPlace ? '季军赛' : `第 ${round.round_id} 轮` }}
          </div>
          <div class="bracket__round-matches">
            <div
              v-for="m in round.matches"
              :key="m.id"
              class="bracket__match"
            >
              <div class="bracket__connector" aria-hidden="true"></div>
              <el-card
                class="bracket__card"
                shadow="hover"
                :body-style="{ padding: '8px 10px' }"
                @click="emit('select', m)"
              >
                <div class="bracket__slot" :class="{ 'bracket__slot--bye': isBye(m) }">
                  <span class="bracket__name">{{ nameOf(m, 'a') }}</span>
                  <span v-if="isBye(m)" class="bracket__bye">轮空</span>
                  <span v-else class="bracket__score">{{ scoreOf(m, 'a') }}</span>
                </div>
                <div class="bracket__slot" :class="{ 'bracket__slot--bye': isBye(m) }">
                  <span class="bracket__name">{{ nameOf(m, 'b') }}</span>
                  <span v-if="isBye(m)" class="bracket__bye">—</span>
                  <span v-else class="bracket__score">{{ scoreOf(m, 'b') }}</span>
                </div>
                <div class="bracket__foot">
                  <el-tag size="small" :type="statusType(m.status)">
                    {{ statusLabel(m.status) }}
                  </el-tag>
                </div>
              </el-card>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- 循环赛 / 瑞士轮：轮次对阵表 -->
    <div v-else class="schedule-chart__rounds">
      <div
        v-for="round in rounds"
        :key="round.round_id"
        class="rounds__group"
      >
        <h3 class="rounds__title">第 {{ round.round_id }} 轮</h3>
        <div class="rounds__matches">
          <el-card
            v-for="m in round.matches"
            :key="m.id"
            class="rounds__card"
            shadow="hover"
            :body-style="{ padding: '10px 12px' }"
            @click="emit('select', m)"
          >
            <div class="rounds__row">
              <span class="rounds__name">{{ nameOf(m, 'a') }}</span>
              <span class="rounds__vs">VS</span>
              <span class="rounds__name">{{ nameOf(m, 'b') }}</span>
            </div>
            <div class="rounds__foot">
              <el-tag size="small" :type="statusType(m.status)">
                {{ statusLabel(m.status) }}
              </el-tag>
              <span v-if="resultText(m)" class="rounds__result">{{ resultText(m) }}</span>
            </div>
          </el-card>
        </div>
      </div>
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

const props = defineProps<{
  rounds: RoundGroup[]
  format: string
}>()

const emit = defineEmits<{
  (e: 'select', match: MatchInfo): void
}>()

const isSingleElim = computed(() => props.format === 'single_elim')

const totalMatches = computed(() =>
  props.rounds.reduce((sum, r) => sum + r.matches.length, 0)
)

// 单败淘汰：把轮次整理为 bracket 列，最后一轮（单场）识别为季军赛侧分支。
interface BracketRound extends RoundGroup {
  isThirdPlace: boolean
}

const bracketRounds = computed<BracketRound[]>(() => {
  const sorted = [...props.rounds].sort((a, b) => a.round_id - b.round_id)
  if (sorted.length === 0) return []
  const last = sorted[sorted.length - 1]
  // 季军赛：最后一轮且仅一场（决赛也是单场，但决赛是倒数第二轮；当只有一轮时视为首轮）。
  const isThirdPlace =
    sorted.length > 1 && last.matches.length === 1
  return sorted.map((r, i) => ({
    ...r,
    isThirdPlace: i === sorted.length - 1 && isThirdPlace,
  }))
})

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

function resultText(m: MatchInfo): string {
  if (!m.result) return ''
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
</script>

<style scoped>
.schedule-chart__empty {
  padding: 8px 0;
}

/* ---------- bracket ---------- */
.schedule-chart__bracket {
  overflow-x: auto;
  padding-bottom: 8px;
}
.bracket {
  display: flex;
  gap: 24px;
  min-width: max-content;
}
.bracket__round {
  display: flex;
  flex-direction: column;
  gap: 12px;
  min-width: 180px;
}
.bracket__round--third {
  border-left: 2px dashed #c0c4cc;
  padding-left: 16px;
}
.bracket__round-title {
  font-size: 13px;
  font-weight: 600;
  color: #606266;
  text-align: center;
  white-space: nowrap;
}
.bracket__round-matches {
  display: flex;
  flex-direction: column;
  gap: 16px;
  flex: 1;
}
.bracket__match {
  position: relative;
}
.bracket__card {
  cursor: pointer;
}
.bracket__slot {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  padding: 2px 0;
}
.bracket__slot--bye {
  opacity: 0.75;
}
.bracket__name {
  flex: 1;
  font-size: 13px;
  font-weight: 600;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.bracket__score {
  font-size: 12px;
  color: #909399;
  flex-shrink: 0;
}
.bracket__bye {
  font-size: 11px;
  color: #e6a23c;
  flex-shrink: 0;
}
.bracket__foot {
  margin-top: 4px;
  display: flex;
  justify-content: flex-end;
}
/* 简单连接线：每张卡片左侧一条竖线，指向下一轮 */
.bracket__connector {
  position: absolute;
  left: -12px;
  top: 50%;
  width: 12px;
  height: 1px;
  background: #dcdfe6;
}
.bracket__round:first-child .bracket__connector {
  display: none;
}

/* ---------- rounds table ---------- */
.schedule-chart__rounds {
  display: flex;
  flex-direction: column;
  gap: 20px;
}
.rounds__title {
  margin: 0 0 10px;
  font-size: 15px;
}
.rounds__matches {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(240px, 1fr));
  gap: 12px;
}
.rounds__card {
  cursor: pointer;
}
.rounds__row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  margin-bottom: 8px;
}
.rounds__name {
  flex: 1;
  text-align: center;
  font-weight: 600;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.rounds__vs {
  color: #c0c4cc;
  font-size: 12px;
}
.rounds__foot {
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.rounds__result {
  font-size: 12px;
  color: #909399;
}
</style>
