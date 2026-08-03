<template>
  <div class="admin-page">
    <div class="page-head">
      <h2>比赛管理</h2>
      <el-button type="primary" @click="openCreate">新建比赛</el-button>
    </div>

    <el-table :data="competitions" v-loading="loading" border stripe>
      <el-table-column prop="id" label="ID" width="70" />
      <el-table-column prop="name" label="名称" min-width="160" />
      <el-table-column prop="participant_type" label="参赛形式" width="110" />
      <el-table-column prop="tournament_format" label="赛制" width="120" />
      <el-table-column prop="gameplay_plugin" label="玩法" width="130" />
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
            size="small"
            type="danger"
            :disabled="!deletable(row.status)"
            @click="remove(row)"
          >
            删除
          </el-button>
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
        <el-form-item label="横幅 URL">
          <el-input v-model="form.banner_url" />
        </el-form-item>
        <el-form-item label="参赛形式">
          <el-radio-group v-model="form.participant_type">
            <el-radio value="team">团队</el-radio>
            <el-radio value="individual">个人</el-radio>
            <el-radio value="mixed">混合</el-radio>
          </el-radio-group>
        </el-form-item>
        <el-form-item label="赛制">
          <el-radio-group v-model="form.tournament_format">
            <el-radio value="round_robin">循环赛</el-radio>
            <el-radio value="swiss">瑞士轮</el-radio>
            <el-radio value="single_elim">单败淘汰</el-radio>
          </el-radio-group>
        </el-form-item>
        <el-form-item v-if="form.tournament_format === 'round_robin'" label="分组数">
          <el-input-number v-model="groupSize" :min="1" />
        </el-form-item>
        <el-form-item v-if="form.tournament_format === 'swiss'" label="轮数">
          <el-input-number v-model="rounds" :min="1" />
        </el-form-item>
        <el-form-item label="玩法插件">
          <el-select v-model="form.gameplay_plugin">
            <el-option label="triangle_occupy" value="triangle_occupy" />
          </el-select>
        </el-form-item>
        <el-form-item label="积分规则">
          <div class="points-editor">
            <div class="points-row" v-for="(r, i) in pointsRows" :key="i">
              <span>第 {{ i + 1 }} 名</span>
              <el-input-number v-model="r.points" :min="0" :step="1" />
              <el-button size="small" text type="danger" @click="pointsRows.splice(i, 1)">
                删除
              </el-button>
            </div>
            <el-button size="small" @click="pointsRows.push({ points: 0 })">添加名次</el-button>
            <div class="points-default">
              默认分
              <el-input-number v-model="defaultPoints" :min="0" :step="1" />
            </div>
          </div>
        </el-form-item>
        <el-form-item label="曲库 JSON">
          <el-input v-model="songLibText" type="textarea" placeholder='{"songs": []}' />
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
  points_rule: Record<string, any>
  gameplay_plugin: string
  song_lib: Record<string, any> | null
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
  tournament_format: 'round_robin',
  gameplay_plugin: 'triangle_occupy',
  referee_ids: [] as number[],
  max_participants: 50,
})
const groupSize = ref(1)
const rounds = ref(5)
const pointsRows = ref<{ points: number }[]>([{ points: 10 }, { points: 6 }, { points: 3 }])
const defaultPoints = ref(1)
const songLibText = ref('')

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
function deletable(s: string) {
  return s === 'draft' || s === 'cancelled' || s === 'finished'
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
  form.tournament_format = 'round_robin'
  form.gameplay_plugin = 'triangle_occupy'
  form.referee_ids = []
  form.max_participants = 50
  groupSize.value = 1
  rounds.value = 5
  pointsRows.value = [{ points: 10 }, { points: 6 }, { points: 3 }]
  defaultPoints.value = 1
  songLibText.value = ''
}

function buildFormatConfig() {
  if (form.tournament_format === 'round_robin') return { group_size: groupSize.value }
  if (form.tournament_format === 'swiss') return { rounds: rounds.value }
  return {}
}

function buildPointsRule() {
  const rank_points: Record<string, number> = {}
  pointsRows.value.forEach((r, i) => {
    rank_points[String(i + 1)] = r.points
  })
  return { rank_points, default: defaultPoints.value }
}

function buildSongLib() {
  const t = songLibText.value.trim()
  if (!t) return null
  try {
    return JSON.parse(t)
  } catch {
    return null
  }
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
  form.gameplay_plugin = row.gameplay_plugin
  form.referee_ids = [...row.referee_ids]
  form.max_participants = row.max_participants
  groupSize.value = row.format_config?.group_size ?? 1
  rounds.value = row.format_config?.rounds ?? 5
  const rp = row.points_rule?.rank_points || {}
  pointsRows.value = Object.entries(rp).map(([, v]) => ({ points: Number(v) }))
  defaultPoints.value = row.points_rule?.default ?? 1
  songLibText.value = row.song_lib ? JSON.stringify(row.song_lib, null, 2) : ''
  dialogVisible.value = true
}

async function save() {
  if (form.name.trim().length < 2) {
    ElMessage.warning('名称至少 2 个字符')
    return
  }
  const songLib = buildSongLib()
  if (songLibText.value.trim() && songLib === null) {
    ElMessage.warning('曲库 JSON 格式不正确')
    return
  }
  const payload = {
    name: form.name.trim(),
    description: form.description || null,
    banner_url: form.banner_url || null,
    participant_type: form.participant_type,
    tournament_format: form.tournament_format,
    format_config: buildFormatConfig(),
    points_rule: buildPointsRule(),
    gameplay_plugin: form.gameplay_plugin,
    song_lib: songLib,
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

async function remove(row: Competition) {
  try {
    await ElMessageBox.confirm(`确认删除比赛「${row.name}」？`, '提示', { type: 'warning' })
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
.points-editor {
  display: flex;
  flex-direction: column;
  gap: 8px;
  width: 100%;
}
.points-row {
  display: flex;
  align-items: center;
  gap: 8px;
}
.points-default {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 4px;
}
</style>
