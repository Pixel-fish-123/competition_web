<template>
  <div class="admin-page">
    <h2>玩法模块</h2>

    <el-card shadow="never">
      <el-alert
        type="info"
        :closable="false"
        show-icon
        title="玩法模块已从比赛流程中解耦"
        description="比赛由裁判人工管理，赛后可导入玩法日志查看详情。"
      />
      <el-empty description="暂无已注册的玩法插件" />
    </el-card>
  </div>
</template>

<script setup lang="ts">
// 玩法插件系统已从比赛流程中解耦：比赛由裁判人工管理（手动录入比分），
// 赛后可导入玩法日志用于展示。本页为静态说明页，不再请求 /api/admin/plugins。
</script>

<style scoped>
.admin-page h2 {
  margin-top: 0;
}
</style>
