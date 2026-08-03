<template>
  <div class="admin-page">
    <h2>玩法模板管理</h2>

    <el-card shadow="never" v-loading="loading">
      <template #header>已注册玩法插件</template>
      <el-empty v-if="!loading && plugins.length === 0" description="暂无已注册的玩法插件" />
      <div v-for="p in plugins" :key="p.name" class="plugin-card">
        <div class="plugin-name">{{ p.name }}</div>
        <div class="plugin-version">v{{ p.version }}</div>
        <div class="plugin-meta">
          <el-tag size="small">内置</el-tag>
          <el-tag size="small" type="success">可用</el-tag>
        </div>
      </div>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import http from '../../api/http'

interface PluginInfo {
  name: string
  version: string
}

const loading = ref(false)
const plugins = ref<PluginInfo[]>([])

onMounted(async () => {
  loading.value = true
  try {
    const { data } = await http.get<PluginInfo[]>('/admin/plugins')
    plugins.value = data
  } catch {
    // 403/401 由 http 拦截器统一提示；其余错误静默，保持空列表。
  } finally {
    loading.value = false
  }
})
</script>

<style scoped>
.admin-page h2 {
  margin-top: 0;
}
.notice {
  margin-bottom: 16px;
}
.plugin-card {
  border: 1px solid #e4e7ed;
  border-radius: 8px;
  padding: 16px;
  max-width: 420px;
}
.plugin-name {
  font-size: 18px;
  font-weight: 600;
}
.plugin-version {
  color: #909399;
  font-size: 13px;
  margin: 4px 0;
}
.plugin-desc {
  margin: 8px 0;
}
.plugin-meta {
  display: flex;
  gap: 8px;
}
</style>
