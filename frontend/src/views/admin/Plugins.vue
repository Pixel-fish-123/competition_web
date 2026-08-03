<template>
  <div class="admin-page">
    <h2>玩法模板管理</h2>

    <el-alert
      type="info"
      :closable="false"
      show-icon
      title="说明"
      description="后端当前未提供玩法模板列表的管理接口（/api/gameplay/* 尚未实现）。此处展示内置玩法模板的静态信息，后续接入后端后可在此扩展为可增删改的模板管理。"
      class="notice"
    />

    <el-card shadow="never">
      <template #header>内置玩法模板</template>
      <div class="plugin-card">
        <div class="plugin-name">triangle_occupy</div>
        <div class="plugin-version">v1.0.0</div>
        <div class="plugin-desc">三角占领 · 赛时控制器</div>
        <div class="plugin-meta">
          <el-tag size="small">内置</el-tag>
          <el-tag size="small" type="success">可用</el-tag>
        </div>
      </div>
    </el-card>
  </div>
</template>

<script setup lang="ts">
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
