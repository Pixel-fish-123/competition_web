<template>
  <div class="rankings">
    <div class="rankings__head">
      <h2>积分排行榜</h2>
      <el-button text type="primary" @click="goCompetitions">
        单场排名在比赛详情页查看 →
      </el-button>
    </div>

    <el-table :data="leaderboard" v-loading="loading" border stripe>
      <el-table-column label="排名" width="80">
        <template #default="{ $index }">
          <span :class="rankClass($index + 1)" class="rankings__rank">
            {{ $index + 1 }}
          </span>
        </template>
      </el-table-column>
      <el-table-column prop="username" label="用户名" min-width="160" />
      <el-table-column prop="total" label="总分" width="110" />
    </el-table>

    <el-empty
      v-if="!loading && leaderboard.length === 0"
      description="暂无排行数据"
      :image-size="100"
    />
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import http from '../api/http'

interface LeaderboardRow {
  user_id: number
  username: string
  total: number
}

const router = useRouter()
const leaderboard = ref<LeaderboardRow[]>([])
const loading = ref(false)

function rankClass(rank: number) {
  if (rank === 1) return 'rankings__rank--gold'
  if (rank === 2) return 'rankings__rank--silver'
  if (rank === 3) return 'rankings__rank--bronze'
  return ''
}

function goCompetitions() {
  router.push('/competitions')
}

async function loadLeaderboard() {
  loading.value = true
  try {
    // 积分已合并为单一 total（admin 手动发放），无 kind 过滤。
    const { data } = await http.get<LeaderboardRow[]>('/points/leaderboard')
    leaderboard.value = data
  } catch {
    leaderboard.value = []
  } finally {
    loading.value = false
  }
}

onMounted(loadLeaderboard)
</script>

<style scoped>
.rankings {
  max-width: 1100px;
  margin: 0 auto;
  min-height: 300px;
}
.rankings__head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
}
.rankings__head h2 {
  margin: 0;
  font-size: 20px;
  border-left: 4px solid #409eff;
  padding-left: 10px;
}
.rankings__rank {
  display: inline-block;
  min-width: 24px;
  text-align: center;
  font-weight: 700;
  border-radius: 4px;
  padding: 1px 6px;
}
.rankings__rank--gold {
  color: #b8860b;
  background: #fdf6e3;
}
.rankings__rank--silver {
  color: #808080;
  background: #f0f0f0;
}
.rankings__rank--bronze {
  color: #a0522d;
  background: #fdf0e6;
}
</style>
