<template>
  <div class="announcements">
    <div class="page-head">
      <h2>公告</h2>
    </div>
    <div v-loading="loading">
      <el-empty v-if="!loading && list.length === 0" description="暂无公告" />
      <div
        v-for="a in list"
        :key="a.id"
        class="ann-item"
        @click="goDetail(a.id)"
      >
        <div class="ann-item__title">
          {{ a.title }}
          <el-tag
            v-if="(a.attachments || []).length > 0"
            size="small"
            type="warning"
          >
            {{ a.attachments.length }} 个附件
          </el-tag>
        </div>
        <div class="ann-item__meta">
          {{ formatTime(a.created_at) }}
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import http from '../api/http'

interface Attachment {
  filename: string
  stored_name: string
  size: number
  content_type: string | null
}

interface AnnouncementRow {
  id: number
  title: string
  body: string | null
  attachments: Attachment[]
  created_at: string
}

const router = useRouter()
const list = ref<AnnouncementRow[]>([])
const loading = ref(false)

function formatTime(iso: string): string {
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return iso
  return d.toLocaleString('zh-CN')
}

function goDetail(id: number): void {
  router.push(`/announcements/${id}`)
}

onMounted(async () => {
  loading.value = true
  try {
    const { data } = await http.get<AnnouncementRow[]>('/announcements')
    list.value = data
  } catch {
    list.value = []
  } finally {
    loading.value = false
  }
})
</script>

<style scoped>
.announcements {
  max-width: 860px;
  margin: 0 auto;
  padding: 0 16px;
}
.page-head h2 {
  font-size: 22px;
  margin: 0 0 16px;
}
.ann-item {
  padding: 16px 20px;
  margin-bottom: 12px;
  border: 1px solid #ebeef5;
  border-radius: 10px;
  background: #fff;
  cursor: pointer;
  transition: box-shadow 0.2s;
}
.ann-item:hover {
  box-shadow: 0 2px 12px rgba(0, 0, 0, 0.08);
}
.ann-item__title {
  font-size: 16px;
  font-weight: 600;
  color: #303133;
  display: flex;
  align-items: center;
  gap: 8px;
}
.ann-item__meta {
  margin-top: 8px;
  font-size: 13px;
  color: #909399;
}
</style>
