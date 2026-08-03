<template>
  <div class="tri-controls">
    <div class="tri-controls__row">
      <el-button
        type="primary"
        :disabled="!selectedCell || gameOver"
        @click="onOccupy"
      >
        占领
      </el-button>
      <el-button
        type="warning"
        :disabled="!selectedCell || gameOver"
        @click="onCancel"
      >
        取消占领
      </el-button>
      <el-button
        type="danger"
        :disabled="!selectedCell || gameOver"
        @click="onReoccupy"
      >
        重占
      </el-button>
    </div>

    <div class="tri-controls__row">
      <el-input-number
        v-model="scoreInput"
        :min="0"
        :max="9999"
        :disabled="!isL1Selected || gameOver"
        placeholder="L1 分数"
        style="width: 140px"
      />
      <el-input-number
        v-model="tpInput"
        :min="0"
        :max="9999"
        :step="0.1"
        :disabled="!isL1Selected || gameOver"
        placeholder="L1 TP"
        style="width: 140px"
      />
    </div>

    <div class="tri-controls__row">
      <el-input-number
        v-model="minutesInput"
        :min="0"
        :max="999"
        :step="1"
        :disabled="gameOver"
        placeholder="时限(分钟)"
        style="width: 140px"
      />
      <el-button
        type="info"
        :disabled="gameOver"
        @click="onSetTime"
      >
        设置时限
      </el-button>
    </div>

    <div class="tri-controls__row">
      <el-button
        type="danger"
        plain
        :disabled="gameOver"
        @click="onEndGame"
      >
        结束对局
      </el-button>
    </div>

    <div v-if="selectedCell" class="tri-controls__selected">
      已选: L{{ selectedCell.layer }}格{{ selectedCell.id }}（{{ selectedCell.task_name || '任务' }}）
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import type { TriangleCell } from './TriangleBoard.vue'

const props = defineProps<{
  selectedCell: TriangleCell | null
  gameOver: boolean
}>()

const emit = defineEmits<{
  (e: 'occupy', payload: { cell_id: number; score?: number; tp?: number }): void
  (e: 'cancel', cell_id: number): void
  (e: 'reoccupy', cell_id: number): void
  (e: 'set-time', minutes: number): void
  (e: 'end-game'): void
}>()

const scoreInput = ref<number | undefined>(undefined)
const tpInput = ref<number | undefined>(undefined)
const minutesInput = ref<number>(25)

const isL1Selected = computed(() => props.selectedCell?.id === 0)

watch(
  () => props.selectedCell,
  () => {
    scoreInput.value = undefined
    tpInput.value = undefined
  },
)

function onOccupy(): void {
  if (!props.selectedCell) return
  const payload: { cell_id: number; score?: number; tp?: number } = {
    cell_id: props.selectedCell.id,
  }
  if (props.selectedCell.id === 0) {
    if (scoreInput.value === undefined) return
    payload.score = scoreInput.value
    if (tpInput.value !== undefined) payload.tp = tpInput.value
  }
  emit('occupy', payload)
}

function onCancel(): void {
  if (!props.selectedCell) return
  emit('cancel', props.selectedCell.id)
}

function onReoccupy(): void {
  if (!props.selectedCell) return
  emit('reoccupy', props.selectedCell.id)
}

function onSetTime(): void {
  emit('set-time', minutesInput.value)
}

function onEndGame(): void {
  emit('end-game')
}
</script>

<style scoped>
.tri-controls {
  display: flex;
  flex-direction: column;
  gap: 12px;
  padding: 16px;
  border: 1px solid #e4e7ed;
  border-radius: 8px;
  background: #fff;
}
.tri-controls__row {
  display: flex;
  gap: 8px;
  align-items: center;
  flex-wrap: wrap;
}
.tri-controls__selected {
  font-size: 13px;
  color: #606266;
}
</style>
