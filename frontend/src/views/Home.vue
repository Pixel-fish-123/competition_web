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
              <el-button type="primary" size="large" round @click="goCompetitions">
                {{ slide.cta }}
              </el-button>
            </div>
          </div>
        </el-carousel-item>
      </el-carousel>
    </section>
  </div>
</template>

<script setup lang="ts">
import { useRouter } from 'vue-router'

const router = useRouter()

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

function goCompetitions() {
  router.push('/competitions')
}
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
</style>
