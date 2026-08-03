<template>
  <header class="header-nav">
    <nav>
      <router-link to="/">首页</router-link>
      <router-link to="/competitions">比赛</router-link>
      <router-link to="/rankings">排行榜</router-link>
      <router-link v-if="auth.isRefereeOrAdmin" to="/admin">后台</router-link>
      <router-link v-if="auth.isLoggedIn" to="/profile">个人中心</router-link>
    </nav>
    <div class="header-nav__auth">
      <template v-if="auth.isLoggedIn">
        <span class="header-nav__user">{{ auth.user?.username }}</span>
        <el-button text type="primary" @click="handleLogout">退出</el-button>
      </template>
      <router-link v-else to="/login">登录</router-link>
    </div>
  </header>
</template>

<script setup lang="ts">
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { useAuthStore } from '../stores/auth'

const router = useRouter()
const auth = useAuthStore()

async function handleLogout() {
  await auth.logout()
  ElMessage.success('已退出登录')
  router.push('/')
}
</script>

<style scoped>
.header-nav {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 24px;
  border-bottom: 1px solid #e4e7ed;
}
.header-nav nav {
  display: flex;
  gap: 16px;
}
.header-nav a {
  text-decoration: none;
  color: #409eff;
}
.header-nav__auth {
  display: flex;
  align-items: center;
  gap: 12px;
}
.header-nav__user {
  color: #606266;
}
</style>
