<template>
  <div class="points-tx">
    <el-table
      v-if="transactions.length > 0"
      :data="transactions"
      border
      stripe
      v-loading="loading"
    >
      <el-table-column label="变动" width="90">
        <template #default="{ row }">
          <span :class="row.amount >= 0 ? 'points-tx__plus' : 'points-tx__minus'">
            {{ row.amount >= 0 ? '+' : '' }}{{ row.amount }}
          </span>
        </template>
      </el-table-column>
      <el-table-column label="类型" width="120">
        <template #default="{ row }">
          <el-tag size="small" :type="kindType(row.kind)">{{ kindLabel(row.kind) }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="reason" label="说明" min-width="160">
        <template #default="{ row }">
          {{ row.reason || '—' }}
        </template>
      </el-table-column>
      <el-table-column label="时间" width="180">
        <template #default="{ row }">
          {{ formatTime(row.created_at) }}
        </template>
      </el-table-column>
    </el-table>
    <el-empty v-else-if="!loading" description="暂无积分流水" :image-size="80" />
  </div>
</template>

<script setup lang="ts">
export interface PointsTransaction {
  id: number
  amount: number
  kind: string
  ref_competition_id?: number | null
  reason: string | null
  created_at: string
}

withDefaults(
  defineProps<{
    transactions: PointsTransaction[]
    loading?: boolean
  }>(),
  { loading: false },
)

const KIND_LABELS: Record<string, string> = {
  competition: '比赛',
  activity: '活动',
  manual: '手动',
  match_win: '比赛获胜',
  match_participation: '参赛奖励',
  admin_adjust: '管理员调整',
  registration: '报名',
}

const KIND_TYPES: Record<string, string> = {
  competition: 'primary',
  activity: 'success',
  manual: 'warning',
  match_win: 'primary',
  match_participation: 'success',
  admin_adjust: 'warning',
  registration: 'info',
}

function kindLabel(k: string) {
  return KIND_LABELS[k] || k
}
function kindType(k: string) {
  return (KIND_TYPES[k] as any) || 'info'
}
function formatTime(t: string) {
  return new Date(t).toLocaleString('zh-CN')
}
</script>

<style scoped>
.points-tx__plus {
  color: #67c23a;
  font-weight: 600;
}
.points-tx__minus {
  color: #f56c6c;
  font-weight: 600;
}
</style>
