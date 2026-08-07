<template>
  <div class="ann-detail" v-loading="loading">
    <el-button text @click="router.back()">← 返回公告列表</el-button>
    <el-empty v-if="!loading && !announcement" description="公告不存在或已删除" />

    <template v-if="announcement">
      <h2 class="ann-detail__title">{{ announcement.title }}</h2>
      <div class="ann-detail__meta">发布于 {{ formatTime(announcement.created_at) }}</div>

      <div v-if="announcement.body" class="ann-detail__body">
        <p v-for="(line, i) in bodyLines" :key="i">{{ line }}</p>
      </div>

      <section v-if="(announcement.attachments || []).length > 0" class="ann-detail__files">
        <h3>附件</h3>
        <div
          v-for="att in announcement.attachments"
          :key="att.stored_name"
          class="ann-detail__file"
        >
          <a :href="downloadUrl(att.stored_name)" download>{{ att.filename }}</a>
          <span class="ann-detail__file-size">（{{ formatSize(att.size) }}）</span>
        </div>
      </section>
    </template>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import http from '../api/http'

interface Attachment {
  filename: string
  stored_name: string
  size: number
  content_type: string | null
}

interface AnnouncementDetail {
  id: number
  title: string
  body: string | null
  attachments: Attachment[]
  created_at: string
}

const route = useRoute()
const router = useRouter()
const announcement = ref<AnnouncementDetail | null>(null)
const loading = ref(false)

const bodyLines = computed(() => (announcement.value?.body ?? '').split('\n'))

function formatTime(iso: string): string {
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return iso
  return d.toLocaleString('zh-CN')
}

function formatSize(size: number): string {
  if (size >= 1024 * 1024) return `${(size / 1024 / 1024).toFixed(1)} MB`
  if (size >= 1024) return `${(size / 1024).toFixed(1)} KB`
  return `${size} B`
}

function downloadUrl(storedName: string): string {
  return `/api/announcements/files/${storedName}`
}

onMounted(async () => {
  loading.value = true
  try {
    const { data } = await http.get<AnnouncementDetail>(`/announcements/${route.params.id}`)
    announcement.value = data
  } catch {
    announcement.value = null
  } finally {
    loading.value = false
  }
})
</script>

<style scoped>
.ann-detail {
  max-width: 860px;
  margin: 0 auto;
  padding: 0 16px;
}
.ann-detail__title {
  font-size: 24px;
  margin: 12px 0 8px;
}
.ann-detail__meta {
  font-size: 13px;
  color: #909399;
  margin-bottom: 16px;
}
.ann-detail__body {
  padding: 16px 20px;
  background: #f8f9fb;
  border-radius: 10px;
  line-height: 1.8;
  color: #303133;
}
.ann-detail__files {
  margin-top: 24px;
}
.ann-detail__files h3 {
  font-size: 16px;
}
.ann-detail__file {
  padding: 10px 0;
  border-bottom: 1px solid #f0f2f5;
}
.ann-detail__file a {
  color: #409eff;
  text-decoration: none;
}
.ann-detail__file-size {
  color: #909399;
  font-size: 13px;
}
</style>
