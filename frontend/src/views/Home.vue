<template>
  <div class="home">
    <!-- 宣传插画轮播位 -->
    <section class="home__hero">
      <el-carousel height="360px" :interval="5000" arrow="always">
        <el-carousel-item v-for="(slide, i) in slides" :key="i">
          <div class="hero-slide" :class="`hero-slide--${i + 1}`">
            <div class="hero-slide__art" aria-hidden="true">
              <svg viewBox="0 0 200 200" class="hero-slide__svg">
                <polygon :points="slide.points" :fill="slide.fill" opacity="0.9" />
                <polygon :points="slide.points2" :fill="slide.fill2" opacity="0.7" />
                <circle :cx="slide.cx" :cy="slide.cy" :r="slide.r" :fill="slide.accent" />
              </svg>
            </div>
            <div class="hero-slide__text">
              <h2>{{ slide.title }}</h2>
              <p>{{ slide.subtitle }}</p>
              <el-button type="primary" size="large" round @click="scrollToList">
                {{ slide.cta }}
              </el-button>
            </div>
          </div>
        </el-carousel-item>
      </el-carousel>
    </section>

    <!-- 比赛列表 -->
    <section ref="listRef" class="home__list">
      <div class="home__list-head">
        <h2>当前 / 即将比赛</h2>
        <el-button text type="primary" @click="$router.push('/competitions')">
          查看全部 →
        </el-button>
      </div>

      <div v-loading="loading" class="home__grid">
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
    </section>
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
const listRef = ref<HTMLElement | null>(null)

const slides = [
  {
    title: '萌新杯音游大赛',
    subtitle: '全新赛季开启，欢迎各路萌新与高手同台竞技',
    cta: '立即报名',
    points: '100,20 180,90 100,160 20,90',
    points2: '100,60 150,100 100,140 50,100',
    fill: '#409eff',
    fill2: '#79bbff',
    cx: 160,
    cy: 40,
    r: 18,
    accent: '#f56c6c',
  },
  {
    title: '三角占领',
    subtitle: '经典玩法回归，策略与手速的巅峰对决',
    cta: '了解赛制',
    points: '100,30 170,140 30,140',
    points2: '100,70 140,130 60,130',
    fill: '#67c23a',
    fill2: '#95d475',
    cx: 40,
    cy: 40,
    r: 22,
    accent: '#e6a23c',
  },
  {
    title: '全新赛季',
    subtitle: '更多玩法、更多奖励，等你来挑战',
    cta: '查看比赛',
    points: '100,20 180,100 100,180 20,100',
    points2: '100,60 140,100 100,140 60,100',
    fill: '#e6a23c',
    fill2: '#f3d19e',
    cx: 170,
    cy: 160,
    r: 16,
    accent: '#409eff',
  },
]

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
  return (STATUS_TYPES[s] as any) || 'info'
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

function scrollToList() {
  listRef.value?.scrollIntoView({ behavior: 'smooth' })
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
.home {
  max-width: 1100px;
  margin: 0 auto;
}
.home__hero {
  margin-bottom: 32px;
  border-radius: 12px;
  overflow: hidden;
}
.hero-slide {
  height: 100%;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 48px;
  color: #fff;
}
.hero-slide--1 {
  background: linear-gradient(135deg, #1f2d3d 0%, #2b4a6f 100%);
}
.hero-slide--2 {
  background: linear-gradient(135deg, #1d3a2a 0%, #2f6b4f 100%);
}
.hero-slide--3 {
  background: linear-gradient(135deg, #3d2f1d 0%, #6b4f2f 100%);
}
.hero-slide__art {
  width: 220px;
  height: 220px;
  display: flex;
  align-items: center;
  justify-content: center;
}
.hero-slide__svg {
  width: 200px;
  height: 200px;
}
.hero-slide__text h2 {
  font-size: 32px;
  margin: 0 0 8px;
}
.hero-slide__text p {
  font-size: 16px;
  opacity: 0.85;
  margin: 0 0 20px;
}
.home__list-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
}
.home__list-head h2 {
  margin: 0;
}
.home__grid {
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
