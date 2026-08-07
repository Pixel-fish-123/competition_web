<template>
  <footer class="site-footer">
    <div class="site-footer__inner">
      <span class="site-footer__status"><i></i> SYSTEM ONLINE</span>
      <span>萌新杯音游赛事平台 <b>/</b> PLAY FAIR. PLAY LOUD.</span>
      <span class="site-footer__code">S01 · 2026</span>
    </div>
  </footer>
</template>

<style scoped>
.site-footer { padding: 24px 0; color: var(--muted); font: 10px 'DM Mono', monospace; letter-spacing: .04em; }
.site-footer__inner { width: min(1320px, calc(100% - 40px)); margin: 0 auto; display: flex; justify-content: space-between; gap: 18px; border-top: 1px solid var(--line); padding-top: 16px; }.site-footer b { margin: 0 8px; color: var(--cyan); }.site-footer__status { display: inline-flex; align-items: center; gap: 7px; color: var(--cyan-dark); }.site-footer__status i { display: block; width: 6px; height: 6px; border-radius: 50%; background: #38b36b; box-shadow: 0 0 0 3px #dff4e7; }.site-footer__code { color: var(--ink-soft); }
@media (max-width: 600px) { .site-footer__inner { width: calc(100% - 32px); flex-wrap: wrap; }.site-footer__inner > span:nth-child(2) { order: 3; width: 100%; } }
</style>
