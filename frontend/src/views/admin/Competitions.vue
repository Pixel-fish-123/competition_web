<template>
  <div class="admin-page">
    <div class="page-head">
      <h2>比赛管理</h2>
      <el-button type="primary" @click="openCreate">新建比赛</el-button>
    </div>

    <el-table :data="competitions" v-loading="loading" border stripe>
      <el-table-column prop="name" label="名称" min-width="160" />
      <el-table-column prop="participant_type" label="参赛形式" width="110" />
      <el-table-column prop="tournament_format" label="赛制" width="120" />
      <el-table-column prop="max_participants" label="人数上限" width="90" />
      <el-table-column label="状态" width="110">
        <template #default="{ row }">
          <el-tag :type="statusType(row.status)">{{ statusLabel(row.status) }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="操作" min-width="260">
        <template #default="{ row }">
          <el-button size="small" @click="openEdit(row)">编辑</el-button>
          <el-button
            v-for="t in nextTransitions(row.status)"
            :key="t"
            size="small"
            type="primary"
            @click="transition(row, t)"
          >
            {{ statusLabel(t) }}
          </el-button>
          <el-button
            v-if="row.status === 'ongoing'"
            size="small"
            type="warning"
            @click="forceFinish(row)"
          >
            强制结束
          </el-button>
          <el-button size="small" type="danger" @click="remove(row)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <el-dialog v-model="dialogVisible" :title="editing ? '编辑比赛' : '新建比赛'" width="640px">
      <el-form label-width="110px">
        <el-form-item label="名称" required>
          <el-input v-model="form.name" />
        </el-form-item>
        <el-form-item label="描述">
          <el-input v-model="form.description" type="textarea" />
        </el-form-item>
        <el-form-item label="头图 URL">
          <el-input v-model="form.banner_url" placeholder="支持图床链接，如 https://.../banner.png" />
        </el-form-item>
        <el-form-item label="参赛形式">
          <el-radio-group v-model="form.participant_type">
            <el-radio value="individual">个人</el-radio>
            <el-radio value="mixed">混合</el-radio>
          </el-radio-group>
        </el-form-item>
        <el-form-item label="赛制">
          <el-radio-group v-model="form.tournament_format">
            <el-radio value="swiss">瑞士轮</el-radio>
            <el-radio value="single_elim">单败淘汰</el-radio>
          </el-radio-group>
          <div class="form-tip">瑞士轮轮数按参赛人数自动调整（ceil(log₂n)+1 轮）</div>
        </el-form-item>
        <el-form-item label="裁判">
          <el-select v-model="form.referee_ids" multiple placeholder="选择裁判" style="width: 100%">
            <el-option
              v-for="r in referees"
              :key="r.id"
              :label="r.username"
              :value="r.id"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="人数上限">
          <el-input-number v-model="form.max_participants" :min="1" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="save">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import http from '../../api/http'

interface Competition {
  id: number
  name: string
  description: string | null
  banner_url: string | null
  participant_type: string
  tournament_format: string
  format_config: Record<string, any>
  referee_ids: number[]
  max_participants: number
  status: string
  created_at: string
}

interface UserRow {
  id: number
  username: string
  role: string
}

const competitions = ref<Competition[]>([])
const loading = ref(false)
const referees = ref<UserRow[]>([])

const dialogVisible = ref(false)
const editing = ref(false)
const saving = ref(false)
const editingId = ref<number | null>(null)

const form = reactive({
  name: '',
  description: '',
  banner_url: '',
  participant_type: 'mixed',
  tournament_format: 'swiss',
  referee_ids: [] as number[],
  max_participants: 50,
})

const STATUS_LABELS: Record<string, string> = {
  draft: '草稿',
  registration: '报名中',
  ongoing: '进行中',
  finished: '已结束',
  cancelled: '已取消',
}
const STATUS_TYPES: Record<string, string> = {
  draft: 'info',
  registration: 'warning',
  ongoing: 'success',
  finished: '',
  cancelled: 'danger',
}
const TRANSITIONS: Record<string, string[]> = {
  draft: ['registration', 'cancelled'],
  registration: ['ongoing', 'cancelled'],
  ongoing: ['finished'],
  finished: [],
  cancelled: [],
}

function statusLabel(s: string) {
  return STATUS_LABELS[s] || s
}
function statusType(s: string) {
  return STATUS_TYPES[s] || 'info'
}
function nextTransitions(s: string) {
  return TRANSITIONS[s] || []
}

async function loadCompetitions() {
  loading.value = true
  try {
    const { data } = await http.get<Competition[]>('/competitions')
    competitions.value = data
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || '加载比赛失败')
  } finally {
    loading.value = false
  }
}

async function loadReferees() {
  try {
    const { data } = await http.get<UserRow[]>('/admin/users')
    referees.value = data.filter((u) => u.role === 'referee')
  } catch {
    referees.value = []
  }
}

function resetForm() {
  form.name = ''
  form.description = ''
  form.banner_url = ''
  form.participant_type = 'mixed'
  form.tournament_format = 'swiss'
  form.referee_ids = []
  form.max_participants = 50
}

function openCreate() {
  editing.value = false
  editingId.value = null
  resetForm()
  dialogVisible.value = true
}

function openEdit(row: Competition) {
  editing.value = true
  editingId.value = row.id
  form.name = row.name
  form.description = row.description || ''
  form.banner_url = row.banner_url || ''
  form.participant_type = row.participant_type
  form.tournament_format = row.tournament_format
  form.referee_ids = [...row.referee_ids]
  form.max_participants = row.max_participants
  dialogVisible.value = true
}

async function save() {
  if (form.name.trim().length < 2) {
    ElMessage.warning('名称至少 2 个字符')
    return
  }
  const payload = {
    name: form.name.trim(),
    description: form.description || null,
    banner_url: form.banner_url || null,
    participant_type: form.participant_type,
    tournament_format: form.tournament_format,
    format_config: {},
    referee_ids: form.referee_ids,
    max_participants: form.max_participants,
  }
  saving.value = true
  try {
    if (editing.value && editingId.value !== null) {
      await http.patch(`/competitions/${editingId.value}`, payload)
      ElMessage.success('比赛已更新')
    } else {
      await http.post('/competitions', payload)
      ElMessage.success('比赛已创建')
    }
    dialogVisible.value = false
    loadCompetitions()
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || '保存失败')
  } finally {
    saving.value = false
  }
}

async function transition(row: Competition, status: string) {
  try {
    await http.post(`/competitions/${row.id}/status`, { status })
    ElMessage.success(`已切换为「${statusLabel(status)}」`)
    loadCompetitions()
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || '状态切换失败')
  }
}

async function forceFinish(row: Competition) {
  try {
    await ElMessageBox.confirm(
      `确认强制结束比赛「${row.name}」？所有未完成对局将标记为作废（不参与排名），且不可恢复。`,
      '强制结束',
      { type: 'warning', confirmButtonText: '强制结束', cancelButtonText: '取消' }
    )
  } catch {
    return
  }
  try {
    await http.post(`/competitions/${row.id}/status`, {
      status: 'finished',
      force: true,
    })
    ElMessage.success('比赛已强制结束')
    loadCompetitions()
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || '强制结束失败')
  }
}

async function remove(row: Competition) {
  try {
    await ElMessageBox.confirm(
      `确认删除比赛「${row.name}」？比赛及其全部赛程/报名/积分记录将被级联删除，且不可恢复。`,
      '提示',
      { type: 'warning' }
    )
  } catch {
    return
  }
  try {
    await http.delete(`/competitions/${row.id}`)
    ElMessage.success('已删除')
    loadCompetitions()
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || '删除失败')
  }
}

onMounted(() => {
  loadCompetitions()
  loadReferees()
})
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
.form-tip {
  width: 100%;
  font-size: 12px;
  color: #909399;
}
</style>
