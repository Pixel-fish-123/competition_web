<template>
  <div class="admin-page">
    <div class="page-head">
      <h2>公告管理</h2>
      <el-button type="primary" @click="openPublish">发布公告</el-button>
    </div>

    <el-table :data="list" v-loading="loading" border stripe>
      <el-table-column prop="title" label="标题" min-width="200" />
      <el-table-column label="附件" width="120">
        <template #default="{ row }">
          <span v-if="(row.attachments || []).length">{{ row.attachments.length }} 个</span>
          <span v-else class="muted">无</span>
        </template>
      </el-table-column>
      <el-table-column label="发布时间" width="180">
        <template #default="{ row }">{{ formatTime(row.created_at) }}</template>
      </el-table-column>
      <el-table-column label="操作" width="140">
        <template #default="{ row }">
          <el-button size="small" type="danger" @click="remove(row)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <el-dialog v-model="publishVisible" title="发布公告" width="560px">
      <el-form label-width="80px">
        <el-form-item label="标题" required>
          <el-input v-model="form.title" maxlength="200" />
        </el-form-item>
        <el-form-item label="正文">
          <el-input v-model="form.body" type="textarea" :rows="5" placeholder="支持换行" />
        </el-form-item>
        <el-form-item label="附件">
          <input type="file" multiple accept=".pdf,.doc,.docx,.zip" @change="onFilesChange" />
          <div v-if="fileNames.length" class="file-names">{{ fileNames.join('、') }}</div>
          <div class="form-tip">支持 pdf / word / zip，单文件不超过 50MB</div>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="publishVisible = false">取消</el-button>
        <el-button type="primary" :loading="publishing" @click="publish">发布</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import http from '../../api/http'

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

const list = ref<AnnouncementRow[]>([])
const loading = ref(false)
const publishVisible = ref(false)
const publishing = ref(false)
const form = ref({ title: '', body: '' })
const selectedFiles = ref<File[]>([])
const fileNames = ref<string[]>([])

function formatTime(iso: string): string {
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return iso
  return d.toLocaleString('zh-CN')
}

async function loadList() {
  loading.value = true
  try {
    const { data } = await http.get<AnnouncementRow[]>('/announcements')
    list.value = data
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || '加载公告失败')
  } finally {
    loading.value = false
  }
}

function openPublish() {
  form.value = { title: '', body: '' }
  selectedFiles.value = []
  fileNames.value = []
  publishVisible.value = true
}

function onFilesChange(event: Event) {
  const input = event.target as HTMLInputElement
  selectedFiles.value = input.files ? Array.from(input.files) : []
  fileNames.value = selectedFiles.value.map((f) => f.name)
}

async function publish() {
  if (form.value.title.trim().length < 1) {
    ElMessage.warning('请输入标题')
    return
  }
  publishing.value = true
  try {
    const data = new FormData()
    data.append('title', form.value.title.trim())
    if (form.value.body.trim()) data.append('body', form.value.body.trim())
    for (const f of selectedFiles.value) data.append('files', f)
    await http.post('/admin/announcements', data)
    ElMessage.success('公告已发布')
    publishVisible.value = false
    await loadList()
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || '发布失败')
  } finally {
    publishing.value = false
  }
}

async function remove(row: AnnouncementRow) {
  try {
    await ElMessageBox.confirm(`确认删除公告「${row.title}」？附件将一并删除。`, '删除公告', {
      type: 'warning',
    })
  } catch {
    return
  }
  try {
    await http.delete(`/admin/announcements/${row.id}`)
    ElMessage.success('已删除')
    await loadList()
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || '删除失败')
  }
}

onMounted(loadList)
</script>

<style scoped>
.admin-page h2 {
  margin-top: 0;
}
.page-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
}
.muted {
  color: #909399;
}
.file-names {
  margin-top: 6px;
  font-size: 13px;
  color: #606266;
}
.form-tip {
  font-size: 12px;
  color: #909399;
  margin-top: 4px;
}
</style>
