<template>
  <div class="admin-layout">
    <aside class="admin-sidebar">
      <div class="admin-brand">管理后台</div>
      <nav class="admin-nav">
        <router-link to="/admin/users" class="admin-nav-item">选手管理</router-link>
        <router-link to="/admin/competitions" class="admin-nav-item">比赛管理</router-link>
        <router-link to="/admin/points" class="admin-nav-item">积分管理</router-link>
        <router-link to="/admin/traffic" class="admin-nav-item">流量监控</router-link>
      </nav>
    </aside>
    <main class="admin-content">
      <router-view />
    </main>
  </div>
</template>

<script setup lang="ts">
</script>

<style scoped>
.admin-layout {
  display: flex;
  gap: 24px;
  align-items: flex-start;
}
.admin-sidebar {
  width: 200px;
  flex-shrink: 0;
  border: 1px solid #e4e7ed;
  border-radius: 8px;
  padding: 16px 0;
  background: #fff;
}
.admin-brand {
  font-size: 16px;
  font-weight: 600;
  padding: 0 20px 12px;
  border-bottom: 1px solid #f0f2f5;
  margin-bottom: 8px;
}
.admin-nav {
  display: flex;
  flex-direction: column;
}
.admin-nav-item {
  display: block;
  padding: 10px 20px;
  color: #303133;
  text-decoration: none;
  font-size: 14px;
}
.admin-nav-item:hover {
  background: #f5f7fa;
  color: #409eff;
}
.admin-nav-item.router-link-active {
  background: #ecf5ff;
  color: #409eff;
  font-weight: 500;
}
.admin-content {
  flex: 1;
  min-width: 0;
}
</style>
