<template>
  <div class="home-page">
    <div class="home-page__grid" aria-hidden="true"></div>
    <section class="hero-shell">
      <div class="hero-copy">
        <div class="eyebrow"><CircleDot :size="13" /> SEASON 01 / OPEN CIRCUIT</div>
        <h1>让每一个<br /><em>节拍</em>都有回响<span>.</span></h1>
        <p class="hero-copy__lead">专为音游玩家打造的社区赛事空间。实时赛程、公开积分与下一场对决，都在这里被清晰记录。</p>
        <div class="hero-actions">
          <router-link class="action action--primary" to="/competitions">查看当前赛事 <ArrowUpRight :size="17" /></router-link>
          <router-link class="action action--quiet" to="/rankings">查看积分榜 <ChevronRight :size="16" /></router-link>
        </div>
        <div class="hero-meta"><span><i></i> LIVE PLATFORM</span><span>EST. 2024</span><span>CN / ONLINE</span></div>
      </div>

      <div class="hero-visual" aria-label="赛事数据可视化装饰">
        <div class="visual-label visual-label--top">SIGNAL / 07 <span>●</span></div>
        <div class="visual-core"><div class="visual-core__ring visual-core__ring--outer"></div><div class="visual-core__ring visual-core__ring--middle"></div><div class="visual-core__ring visual-core__ring--inner"></div><div class="visual-core__pulse"></div><span class="visual-core__crosshair">+</span></div>
        <div class="visual-label visual-label--bottom"><span>SYNC RATE</span><strong>98.6%</strong></div>
        <div class="visual-axis visual-axis--one"></div><div class="visual-axis visual-axis--two"></div>
        <span class="visual-number visual-number--one">01</span><span class="visual-number visual-number--two">07</span><span class="visual-number visual-number--three">24</span>
      </div>
    </section>

    <section class="current-event" aria-labelledby="current-event-title">
      <div class="section-kicker"><span>01</span><span id="current-event-title">CURRENT EVENT</span></div>
      <div v-if="currentCompetition" class="current-event__main">
        <div><span class="live-tag"><i></i> 正在进行</span><h2>{{ currentCompetition.name }}</h2><p><CalendarDays :size="15" /> {{ formatDate(currentCompetition.start_time) }} / {{ formatLabel(currentCompetition.tournament_format) }}</p></div>
        <div class="current-event__status"><strong>LIVE</strong><small>赛事进行中</small></div>
        <router-link class="panel-link" :to="`/competitions/${currentCompetition.id}`">进入比赛 <ChevronRight :size="16" /></router-link>
      </div>
      <div v-else class="current-event__empty"><CircleDot :size="18" /><span>当前无进行比赛</span><router-link class="panel-link" to="/competitions">查看赛事列表 <ChevronRight :size="16" /></router-link></div>
    </section>

    <section class="feature-section" aria-labelledby="feature-title">
      <div class="section-heading"><div><div class="section-kicker"><span>02</span><span>WHY ARENA</span></div><h2 id="feature-title">为比赛而生的<br /><em>清晰系统</em></h2></div><p>从报名到最终排名，每一条信息都保持可见、可追踪、可复盘。</p></div>
      <div class="feature-grid">
        <article class="feature-card feature-card--cyan"><span class="feature-card__number">A / 01</span><div class="feature-card__icon"><Gauge :size="23" /></div><h3>实时赛程</h3><p>对局状态与比赛进度实时同步，不错过任何一次交锋。</p><router-link to="/competitions">浏览赛程 <ArrowUpRight :size="15" /></router-link></article>
        <article class="feature-card"><span class="feature-card__number">B / 02</span><div class="feature-card__icon"><Medal :size="23" /></div><h3>公开积分</h3><p>用清晰的胜负记录和累计积分，见证每一次成长。</p><router-link to="/rankings">查看排名 <ArrowUpRight :size="15" /></router-link></article>
        <article class="feature-card feature-card--orange"><span class="feature-card__number">C / 03</span><div class="feature-card__icon"><Radio :size="23" /></div><h3>社区联赛</h3><p>小规模、高频率、低门槛，找到与你同频的对手。</p><router-link to="/announcements">阅读公告 <ArrowUpRight :size="15" /></router-link></article>
      </div>
    </section>

    <section class="closing-note"><span class="closing-note__line"></span><p>准备好进入下一场对局了吗？<br /><strong>你的节拍，值得被看见。</strong></p><router-link class="round-arrow" to="/competitions" aria-label="进入赛事中心"><ArrowUpRight :size="22" /></router-link></section>
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { ArrowUpRight, CalendarDays, ChevronRight, CircleDot, Gauge, Medal, Radio } from '@lucide/vue'
import http from '../api/http'

interface Competition {
  id: number
  name: string
  tournament_format: string
  status: string
  start_time: string | null
}

const currentCompetition = ref<Competition | null>(null)

function formatDate(value: string | null) {
  if (!value) return '时间待定'
  return new Intl.DateTimeFormat('zh-CN', { year: 'numeric', month: '2-digit', day: '2-digit' }).format(new Date(value)).replaceAll('/', '.')
}

function formatLabel(value: string) {
  return value === 'single_elim' ? '单败淘汰' : '瑞士轮'
}

async function loadCurrentCompetition() {
  try {
    const { data } = await http.get<Competition[]>('/competitions')
    currentCompetition.value = data.find((competition) => competition.status === 'ongoing') ?? null
  } catch {
    currentCompetition.value = null
  }
}

onMounted(() => {
  loadCurrentCompetition()
})
</script>

<style scoped>
.home-page { position: relative; overflow: hidden; padding: 62px max(20px, calc((100% - 1320px) / 2)) 20px; background: var(--canvas); }.home-page__grid { position: absolute; inset: 0; z-index: 0; pointer-events: none; opacity: .48; background-image: linear-gradient(to right, rgba(12, 148, 165, .07) 1px, transparent 1px), linear-gradient(to bottom, rgba(12, 148, 165, .07) 1px, transparent 1px); background-size: 76px 76px; mask-image: linear-gradient(to bottom, #000, transparent 72%); }
.hero-shell, .countdown-panel, .feature-section, .signal-strip, .closing-note { position: relative; z-index: 1; }.hero-shell { min-height: 520px; display: grid; grid-template-columns: 1.03fr .97fr; align-items: center; gap: 50px; }.eyebrow, .section-kicker { display: flex; align-items: center; gap: 9px; color: var(--cyan-dark); font: 11px 'DM Mono', monospace; letter-spacing: .14em; }.eyebrow svg { color: var(--orange); }.hero-copy h1 { max-width: 660px; margin: 19px 0 23px; color: var(--ink); font: 700 clamp(54px, 7.3vw, 104px)/.89 'Barlow Condensed', sans-serif; letter-spacing: -.025em; }.hero-copy h1 em, .section-heading em { color: var(--cyan); font-style: normal; }.hero-copy h1 span { color: var(--orange); }.hero-copy__lead { max-width: 450px; margin: 0; color: var(--ink-soft); font-size: 15px; line-height: 1.9; }.hero-actions { display: flex; flex-wrap: wrap; align-items: center; gap: 23px; margin-top: 33px; }.action { display: inline-flex; align-items: center; gap: 8px; text-decoration: none; font-size: 13px; font-weight: 800; transition: transform .2s ease, color .2s ease, background .2s ease; }.action--primary { padding: 13px 17px; color: #fff; background: var(--ink); }.action--primary:hover { background: var(--cyan-dark); transform: translateY(-2px); }.action--quiet { color: var(--ink-soft); }.action--quiet:hover { color: var(--cyan-dark); }.hero-meta { display: flex; gap: 22px; margin-top: 54px; color: var(--muted); font: 10px 'DM Mono', monospace; letter-spacing: .05em; }.hero-meta span:first-child { color: var(--cyan-dark); }.hero-meta i { display: inline-block; width: 6px; height: 6px; margin-right: 6px; border-radius: 50%; background: #37ae67; box-shadow: 0 0 0 3px #dff4e7; }
.hero-visual { position: relative; min-height: 450px; }.visual-core { position: absolute; top: 50%; left: 50%; width: min(35vw, 400px); aspect-ratio: 1; transform: translate(-50%, -50%); }.visual-core::before { position: absolute; inset: 18%; border: 1px dashed rgba(12, 148, 165, .38); border-radius: 50%; content: ''; animation: spin 24s linear infinite; }.visual-core__ring { position: absolute; border-radius: 50%; }.visual-core__ring--outer { inset: 3%; border: 1px solid var(--line-strong); border-right-color: var(--cyan); transform: rotate(-30deg); }.visual-core__ring--middle { inset: 14%; border: 1px solid rgba(12, 148, 165, .48); border-left-color: transparent; transform: rotate(44deg); }.visual-core__ring--inner { inset: 30%; border: 1px solid var(--cyan); border-bottom-color: transparent; transform: rotate(110deg); }.visual-core__pulse { position: absolute; inset: 43%; background: var(--cyan); box-shadow: 0 0 0 11px var(--cyan-pale), 0 0 0 22px rgba(12, 148, 165, .1); transform: rotate(45deg); animation: pulse 2.6s ease-in-out infinite; }.visual-core__crosshair { position: absolute; top: 50%; left: 50%; z-index: 2; color: #fff; font: 22px 'DM Mono', monospace; transform: translate(-50%, -50%); }.visual-label { position: absolute; z-index: 2; color: var(--ink-soft); font: 10px 'DM Mono', monospace; letter-spacing: .08em; }.visual-label span { color: var(--orange); }.visual-label--top { top: 41px; right: 9%; }.visual-label--bottom { right: 3%; bottom: 52px; display: grid; gap: 5px; border-left: 2px solid var(--orange); padding-left: 10px; }.visual-label--bottom strong { color: var(--ink); font: 24px 'Barlow Condensed', sans-serif; letter-spacing: .04em; }.visual-axis { position: absolute; background: var(--line-strong); }.visual-axis--one { top: 15%; right: 0; width: 1px; height: 72%; }.visual-axis--two { bottom: 15%; left: 6%; width: 58%; height: 1px; }.visual-number { position: absolute; color: var(--line-strong); font: 12px 'DM Mono', monospace; }.visual-number--one { top: 13%; left: 7%; }.visual-number--two { top: 28%; right: 1%; color: var(--cyan); }.visual-number--three { bottom: 12%; left: 3%; color: var(--orange); }
.countdown-panel { margin-top: 20px; border: 1px solid var(--line-strong); background: var(--paper); }.section-kicker { gap: 12px; padding: 18px 22px; border-bottom: 1px solid var(--line); }.section-kicker span:first-child { color: var(--orange); }.countdown-panel__main { display: grid; grid-template-columns: 1.2fr 1fr auto; align-items: center; gap: 26px; padding: 25px 22px; }.live-tag { color: var(--cyan-dark); font: 10px 'DM Mono', monospace; }.live-tag i { display: inline-block; width: 6px; height: 6px; margin-right: 6px; border-radius: 50%; background: var(--orange); }.countdown-panel h2 { margin: 8px 0 7px; font: 600 27px 'Barlow Condensed', sans-serif; letter-spacing: .02em; }.countdown-panel p { display: flex; align-items: center; gap: 7px; margin: 0; color: var(--muted); font-size: 12px; }.countdown { display: flex; align-items: center; justify-content: center; gap: 10px; }.countdown div { display: grid; min-width: 47px; gap: 1px; text-align: center; }.countdown strong { font: 600 33px 'DM Mono', monospace; letter-spacing: -.08em; }.countdown small { color: var(--muted); font: 8px 'DM Mono', monospace; }.countdown b { color: var(--orange); font: 20px 'DM Mono', monospace; }.panel-link { display: inline-flex; align-items: center; gap: 5px; color: var(--cyan-dark); font-size: 12px; font-weight: 800; text-decoration: none; white-space: nowrap; }.panel-link:hover { color: var(--ink); }
.feature-section { padding: 104px 0 88px; }.section-heading { display: flex; align-items: end; justify-content: space-between; gap: 30px; }.section-heading h2 { margin: 17px 0 0; font: 600 clamp(42px, 5vw, 68px)/.9 'Barlow Condensed', sans-serif; letter-spacing: -.02em; }.section-heading p { max-width: 280px; margin: 0 0 4px; color: var(--ink-soft); font-size: 13px; line-height: 1.8; }.feature-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 14px; margin-top: 40px; }.feature-card { position: relative; min-height: 273px; padding: 25px; border: 1px solid var(--line); background: var(--paper); transition: transform .25s ease, box-shadow .25s ease; }.feature-card:hover { transform: translateY(-5px); box-shadow: 0 18px 35px rgba(24, 35, 48, .09); }.feature-card--cyan { border-top: 3px solid var(--cyan); }.feature-card--orange { border-top: 3px solid var(--orange); }.feature-card__number { color: var(--muted); font: 10px 'DM Mono', monospace; }.feature-card__icon { display: flex; align-items: center; justify-content: center; width: 47px; height: 47px; margin: 38px 0 19px; color: var(--cyan-dark); border: 1px solid var(--line-strong); background: var(--cyan-pale); }.feature-card--orange .feature-card__icon { color: #bb6815; background: var(--orange-pale); }.feature-card h3 { margin: 0 0 9px; font: 600 27px 'Barlow Condensed', sans-serif; }.feature-card p { max-width: 250px; margin: 0; color: var(--ink-soft); font-size: 12px; line-height: 1.8; }.feature-card a { position: absolute; right: 25px; bottom: 27px; display: inline-flex; align-items: center; gap: 5px; color: var(--cyan-dark); font-size: 11px; font-weight: 800; text-decoration: none; }.feature-card a:hover { color: var(--ink); }
.signal-strip { display: grid; grid-template-columns: repeat(4, 1fr); border-top: 1px solid var(--line-strong); border-bottom: 1px solid var(--line-strong); background: rgba(255,255,255,.42); }.signal-strip > div { display: grid; grid-template-columns: auto 1fr; column-gap: 10px; align-items: center; padding: 20px 18px; border-right: 1px solid var(--line); }.signal-strip > div:last-child { border-right: 0; }.signal-strip svg { grid-row: span 2; color: var(--cyan); }.signal-strip strong { font: 600 27px 'DM Mono', monospace; line-height: 1; }.signal-strip strong span { color: var(--orange); font-size: 17px; }.signal-strip small { color: var(--muted); font: 8px 'DM Mono', monospace; letter-spacing: .05em; }.closing-note { display: flex; align-items: center; justify-content: center; gap: 30px; padding: 90px 0 60px; text-align: center; }.closing-note__line { width: 65px; height: 1px; background: var(--orange); }.closing-note p { margin: 0; color: var(--muted); font-size: 13px; line-height: 1.8; }.closing-note strong { color: var(--ink); font-size: 20px; }.round-arrow { display: flex; align-items: center; justify-content: center; width: 53px; height: 53px; color: #fff; background: var(--cyan); transition: transform .2s ease, background .2s ease; }.round-arrow:hover { background: var(--ink); transform: rotate(45deg); }.round-arrow:hover svg { transform: rotate(-45deg); }
@keyframes spin { to { transform: rotate(330deg); } } @keyframes pulse { 0%, 100% { opacity: .84; transform: rotate(45deg) scale(.88); } 50% { opacity: 1; transform: rotate(45deg) scale(1); } }
.hero-copy h1 { font-family: 'Microsoft YaHei', 'Noto Sans SC', sans-serif; font-weight: 800; line-height: 1.08; letter-spacing: -.06em; word-break: keep-all; }
.section-heading h2, .current-event h2 { font-family: 'Microsoft YaHei', 'Noto Sans SC', sans-serif; font-weight: 800; line-height: 1.15; }
.current-event { margin-top: 20px; border: 1px solid var(--line-strong); background: var(--paper); }
.current-event__main { display: grid; grid-template-columns: 1.2fr auto auto; align-items: center; gap: 30px; padding: 25px 22px; }
.current-event h2 { margin: 9px 0 8px; font-size: 25px; letter-spacing: -.04em; }
.current-event p { display: flex; align-items: center; gap: 7px; margin: 0; color: var(--muted); font-size: 12px; }
.current-event__status { display: grid; gap: 3px; min-width: 86px; border-left: 1px solid var(--line); padding-left: 24px; }
.current-event__status strong { color: var(--cyan-dark); font: 700 24px 'DM Mono', monospace; }.current-event__status small { color: var(--muted); font-size: 10px; }.current-event__empty { display: flex; align-items: center; gap: 12px; padding: 30px 22px; color: var(--muted); font-size: 14px; }.current-event__empty > svg { color: var(--orange); }.current-event__empty .panel-link { margin-left: auto; }
@media (max-width: 900px) { .home-page { padding-top: 35px; }.hero-shell { min-height: auto; grid-template-columns: 1fr; gap: 0; }.hero-copy h1 { max-width: 500px; }.hero-visual { min-height: 340px; margin-top: -10px; }.visual-core { width: min(54vw, 330px); }.countdown-panel__main { grid-template-columns: 1fr auto; }.panel-link { grid-column: 1 / -1; padding-top: 4px; }.feature-section { padding-top: 75px; } }
@media (max-width: 620px) { .home-page { padding-right: 16px; padding-left: 16px; }.hero-copy h1 { font-size: clamp(48px, 15vw, 76px); }.hero-copy__lead { font-size: 13px; }.hero-meta { gap: 12px; margin-top: 37px; font-size: 8px; }.hero-visual { min-height: 285px; }.visual-core { width: 290px; }.visual-label--top { top: 10px; right: 3%; }.visual-label--bottom { right: 0; bottom: 18px; }.section-kicker { padding: 14px 16px; }.section-heading { display: block; }.section-heading p { margin-top: 22px; }.feature-grid { grid-template-columns: 1fr; margin-top: 28px; }.feature-card { min-height: 240px; }.current-event__main { display: block; padding: 22px 16px; }.current-event__status { display: inline-grid; margin: 22px 0 17px; border-left: 0; border-top: 1px solid var(--line); padding: 12px 0 0; }.current-event__empty { align-items: flex-start; flex-wrap: wrap; padding: 24px 16px; }.current-event__empty .panel-link { width: 100%; margin-left: 30px; }.closing-note { gap: 16px; padding: 65px 0 35px; }.closing-note__line { width: 25px; }.closing-note strong { font-size: 17px; } }
</style>
