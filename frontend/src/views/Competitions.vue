<template>
  <div class="page">
    <div class="page__head">
      <h1>竞赛列表</h1>
    </div>

    <div v-loading="loading" class="comp-list">
      <el-empty v-if="!loading && competitions.length === 0" description="暂无比赛" />
      <div
        v-for="c in competitions"
        :key="c.id"
        class="comp-row"
        @click="goDetail(c)"
      >
        <div class="comp-row__main">
          <span class="comp-row__name">{{ c.name }}</span>
          <el-tag size="small" :type="statusType(c.status)">
            {{ statusLabel(c.status) }}
          </el-tag>
        </div>
        <div class="comp-row__meta">
          <span>{{ formatLabel(c.tournament_format) }}</span>
          <span>{{ participantLabel(c.participant_type) }}</span>
          <span>上限 {{ c.max_participants }} 人</span>
        </div>
        <div class="comp-row__action">
          <el-button
            size="small"
            :type="c.status === 'registration' ? 'primary' : 'default'"
            @click.stop="goDetail(c)"
          >
            {{ c.status === 'registration' ? '立即报名' : '查看详情' }}
          </el-button>
        </div>
      </div>
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
  max-width: 1000px;
  margin: 0 auto;
}
.page__head {
  margin-bottom: 16px;
}
.page__head h1 {
  margin: 0;
}
.comp-list {
  display: flex;
  flex-direction: column;
  min-height: 120px;
}
.comp-row {
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 14px 16px;
  border-bottom: 1px solid #ebeef5;
  cursor: pointer;
  transition: background-color 0.2s;
}
.comp-row:hover {
  background-color: #f5f7fa;
}
.comp-row__main {
  display: flex;
  align-items: center;
  gap: 10px;
  flex: 1;
  min-width: 0;
}
.comp-row__name {
  font-size: 15px;
  font-weight: 600;
  color: #303133;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.comp-row__meta {
  display: flex;
  align-items: center;
  gap: 16px;
  font-size: 13px;
  color: #909399;
  white-space: nowrap;
}
.comp-row__action {
  flex-shrink: 0;
}
@media (max-width: 640px) {
  .comp-row {
    flex-wrap: wrap;
    gap: 8px 16px;
  }
  .comp-row__main {
    flex: 1 1 100%;
  }
  .comp-row__meta {
    flex: 1 1 auto;
    flex-wrap: wrap;
    gap: 8px 16px;
  }
}
</style>
