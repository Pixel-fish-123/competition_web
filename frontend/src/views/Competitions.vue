<template>
  <div class="page">
    <div class="page__head">
      <h1>竞赛列表</h1>
    </div>

    <div v-loading="loading" class="comp-grid">
      <el-empty v-if="!loading && competitions.length === 0" description="暂无比赛" />
      <el-card
        v-for="c in competitions"
        :key="c.id"
        class="comp-card"
        shadow="hover"
        @click="goDetail(c)"
      >
        <div class="comp-card__banner" :class="`banner-${(c.id % 4) + 1}`">
          <span class="comp-card__banner-text">{{ c.name }}</span>
        </div>
        <div class="comp-card__body">
          <div class="comp-card__title-row">
            <h3>{{ c.name }}</h3>
            <el-tag :type="statusType(c.status)" size="small" effect="dark">
              {{ statusLabel(c.status) }}
            </el-tag>
          </div>
          <p class="comp-card__desc">{{ c.description || '暂无描述' }}</p>
          <div class="comp-card__meta">
            <span>{{ participantLabel(c.participant_type) }}</span>
            <span>{{ formatLabel(c.tournament_format) }}</span>
            <span>上限 {{ c.max_participants }}</span>
          </div>
          <div class="comp-card__actions">
            <el-button
              type="primary"
              :disabled="c.status !== 'registration'"
              @click.stop="goDetail(c)"
            >
              {{ c.status === 'registration' ? '立即报名' : '查看详情' }}
            </el-button>
          </div>
        </div>
      </el-card>
    </div>
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import http from '../api/http'

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

const router = useRouter()
const competitions = ref<Competition[]>([])
const loading = ref(false)

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
  return STATUS_TYPES[s] || 'info'
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

function goDetail(c: Competition) {
  router.push(`/competitions/${c.id}`)
}

async function loadCompetitions() {
  loading.value = true
  try {
    const { data } = await http.get<Competition[]>('/competitions')
    competitions.value = data
  } catch {
    competitions.value = []
  } finally {
    loading.value = false
  }
}

onMounted(loadCompetitions)
</script>

<style scoped>
.page {
  max-width: 1100px;
  margin: 0 auto;
}
.page__head {
  margin-bottom: 16px;
}
.page__head h1 {
  margin: 0;
}
.comp-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
  gap: 20px;
  min-height: 120px;
}
.comp-card {
  cursor: pointer;
}
.comp-card__banner {
  height: 120px;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #fff;
  font-size: 20px;
  font-weight: 600;
  border-radius: 4px;
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
.comp-card__body {
  padding: 4px 0;
}
.comp-card__title-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}
.comp-card__title-row h3 {
  margin: 0;
  font-size: 18px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.comp-card__desc {
  color: #909399;
  font-size: 13px;
  margin: 8px 0;
  min-height: 20px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.comp-card__meta {
  display: flex;
  gap: 12px;
  font-size: 13px;
  color: #606266;
  margin-bottom: 12px;
}
.comp-card__actions {
  text-align: right;
}
</style>
