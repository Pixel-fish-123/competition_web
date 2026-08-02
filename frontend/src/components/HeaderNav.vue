<template>
  <header class="header-nav">
    <nav>
      <router-link to="/">首页</router-link>
      <router-link to="/competitions">竞赛</router-link>
      <router-link to="/login">登录</router-link>
      <router-link to="/admin">管理</router-link>
      <router-link to="/profile">个人中心</router-link>
    </nav>
  </header>
</template>

<script setup lang="ts">
</script>

<style scoped>
.header-nav {
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
</style>
