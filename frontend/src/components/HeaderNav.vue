<template>
  <header class="site-header">
    <div class="site-header__inner">
      <router-link class="brand" to="/" aria-label="返回首页">
        <span class="brand__mark"><span></span><span></span><span></span></span>
        <span class="brand__copy">
          <strong>萌新杯</strong>
          <small>RHYTHM / ARENA</small>
        </span>
      </router-link>

      <button
        class="menu-toggle"
        type="button"
        :aria-expanded="menuOpen"
        aria-label="打开导航菜单"
        @click="menuOpen = !menuOpen"
      >
        <Menu v-if="!menuOpen" :size="20" />
        <X v-else :size="20" />
      </button>

      <nav class="site-nav" :class="{ 'site-nav--open': menuOpen }" aria-label="主导航">
        <router-link to="/" @click="menuOpen = false">首页</router-link>
        <router-link to="/competitions" @click="menuOpen = false">赛事中心</router-link>
        <router-link to="/rankings" @click="menuOpen = false">积分榜</router-link>
        <router-link to="/announcements" @click="menuOpen = false">公告</router-link>
        <router-link v-if="auth.user?.role === 'admin'" to="/admin" @click="menuOpen = false">管理台</router-link>
      </nav>

      <div class="site-header__auth">
        <template v-if="auth.isLoggedIn">
          <router-link class="user-chip" to="/profile">
            <span class="user-chip__dot"></span>
            {{ auth.user?.nickname || auth.user?.username }}
          </router-link>
          <button class="logout-button" type="button" @click="handleLogout">退出</button>
        </template>
        <router-link v-else class="login-button" to="/login">登录 / 注册 <ArrowUpRight :size="15" /></router-link>
      </div>
    </div>
  </header>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { ArrowUpRight, Menu, X } from '@lucide/vue'
import { useAuthStore } from '../stores/auth'

const router = useRouter()
const auth = useAuthStore()
const menuOpen = ref(false)

async function handleLogout() {
  await auth.logout()
  menuOpen.value = false
  ElMessage.success('已退出登录')
  router.push('/')
}
</script>

<style scoped>
.site-header { position: sticky; top: 0; z-index: 20; background: rgba(255, 255, 255, 0.94); border-bottom: 1px solid var(--line); backdrop-filter: blur(14px); }
.site-header__inner { width: min(1320px, calc(100% - 40px)); min-height: 74px; margin: 0 auto; display: flex; align-items: center; gap: 44px; }
.brand { display: inline-flex; align-items: center; gap: 11px; text-decoration: none; flex-shrink: 0; }
.brand__mark { display: flex; align-items: flex-end; gap: 3px; width: 28px; height: 28px; padding: 4px; background: var(--ink); transform: skew(-10deg); }
.brand__mark span { display: block; flex: 1; background: var(--cyan); }
.brand__mark span:nth-child(1) { height: 45%; }.brand__mark span:nth-child(2) { height: 72%; background: #fff; }.brand__mark span:nth-child(3) { height: 100%; }
.brand__copy { display: grid; gap: 1px; line-height: 1; }.brand__copy strong { font-family: 'Barlow Condensed', sans-serif; font-size: 22px; letter-spacing: .08em; }.brand__copy small { color: var(--muted); font: 9px 'DM Mono', monospace; letter-spacing: .16em; }
.site-nav { display: flex; align-items: center; gap: 30px; height: 74px; }.site-nav a { position: relative; display: inline-flex; align-items: center; height: 100%; color: var(--ink-soft); font-size: 13px; font-weight: 700; text-decoration: none; transition: color .2s ease; }.site-nav a::after { position: absolute; right: 0; bottom: -1px; left: 0; height: 3px; background: var(--cyan); content: ''; transform: scaleX(0); transition: transform .2s ease; }.site-nav a:hover, .site-nav a.router-link-active { color: var(--ink); }.site-nav a.router-link-exact-active::after, .site-nav a.router-link-active::after { transform: scaleX(1); }
.site-header__auth { display: flex; align-items: center; gap: 14px; margin-left: auto; font-size: 12px; }.user-chip { display: inline-flex; align-items: center; gap: 8px; color: var(--ink); font-weight: 700; text-decoration: none; }.user-chip__dot { width: 7px; height: 7px; border-radius: 50%; background: var(--cyan); box-shadow: 0 0 0 4px var(--cyan-pale); }.logout-button { padding: 4px; border: 0; color: var(--muted); background: transparent; cursor: pointer; }.logout-button:hover { color: var(--ink); }.login-button { display: inline-flex; align-items: center; gap: 6px; padding: 10px 14px; color: #fff; background: var(--ink); text-decoration: none; transition: background .2s ease, transform .2s ease; }.login-button:hover { background: var(--cyan-dark); transform: translateY(-1px); }
.menu-toggle { display: none; border: 1px solid var(--line); padding: 9px; color: var(--ink); background: #fff; cursor: pointer; }
@media (max-width: 800px) { .site-header__inner { width: min(100% - 32px, 620px); gap: 16px; }.menu-toggle { display: inline-flex; margin-left: auto; }.site-nav { position: absolute; top: 74px; right: 16px; left: 16px; display: none; height: auto; padding: 8px; border: 1px solid var(--line); background: #fff; box-shadow: 0 14px 30px rgba(24, 35, 48, .12); }.site-nav--open { display: grid; gap: 0; }.site-nav a { height: 44px; padding: 0 12px; }.site-nav a::after { right: auto; bottom: 8px; left: 12px; width: 18px; height: 2px; }.site-header__auth { margin-left: 0; }.user-chip { display: none; }.login-button { padding: 9px 10px; font-size: 11px; } }
@media (max-width: 420px) { .site-header__inner { width: calc(100% - 24px); }.brand__copy small { display: none; }.brand__copy strong { font-size: 20px; }.site-header__auth { margin-left: 0; }.login-button { padding-inline: 8px; } }
</style>
