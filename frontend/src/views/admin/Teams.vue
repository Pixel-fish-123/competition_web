<template>
  <div class="admin-page">
    <div class="page-head">
      <h2>团队管理</h2>
      <el-button type="primary" @click="openCreate">创建团队</el-button>
    </div>

    <el-table :data="teams" v-loading="loading" border stripe>
      <el-table-column prop="name" label="团队名" min-width="140" />
      <el-table-column label="队长" min-width="120">
        <template #default="{ row }">
          {{ row.captain_nickname || row.captain_username || `用户#${row.captain_id}` }}
        </template>
      </el-table-column>
      <el-table-column label="成员" min-width="200">
        <template #default="{ row }">
          <span
            v-for="m in row.members"
            :key="m.id"
            class="member-chip"
          >
            {{ m.nickname || m.username }}
          </span>
        </template>
      </el-table-column>
      <el-table-column prop="member_count" label="人数" width="70" />
      <el-table-column label="报名状态" width="100">
        <template #default="{ row }">
          <el-tag :type="row.has_registrations ? 'warning' : 'info'" size="small">
            {{ row.has_registrations ? '已有报名' : '未报名' }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="150">
        <template #default="{ row }">
          <el-button size="small" @click="openEdit(row)">编辑</el-button>
          <el-button size="small" type="danger" :loading="deletingId === row.id" @click="onDelete(row)">
            删除
          </el-button>
        </template>
      </el-table-column>
    </el-table>

    <el-dialog v-model="dialogVisible" :title="editing ? '编辑团队' : '创建团队'" width="480px">
      <el-form label-width="80px">
        <el-form-item label="团队名" required>
          <el-input v-model="form.name" placeholder="2-20 个字符" maxlength="20" />
        </el-form-item>
        <el-form-item label="队长" required>
          <el-select
            v-model="form.captain_id"
            filterable
            placeholder="选择队长"
            style="width: 100%"
            :disabled="editing?.has_registrations"
          >
            <el-option
              v-for="u in users"
              :key="u.id"
              :label="`${u.nickname || u.username} (${u.username})`"
              :value="u.id"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="成员" required>
          <el-select
            v-model="form.member_ids"
            multiple
            filterable
            placeholder="选择成员（1-3 人，含队长）"
            style="width: 100%"
            :disabled="editing?.has_registrations"
          >
            <el-option
              v-for="u in users"
              :key="u.id"
              :label="`${u.nickname || u.username} (${u.username})`"
              :value="u.id"
            />
          </el-select>
        </el-form-item>
        <div v-if="editing?.has_registrations" class="form-tip">
          该团队已有报名记录，只能修改团队名称。
        </div>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="onSave">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import http from '../../api/http'

interface TeamMember {
  id: number
  user_id: number
  username: string
  nickname: string | null
}
interface TeamRow {
  id: number
  name: string
  captain_id: number
  captain_username: string | null
  captain_nickname: string | null
  member_count: number
  has_registrations: boolean
  members: TeamMember[]
}
interface UserRow {
  id: number
  username: string
  nickname: string | null
}

const teams = ref<TeamRow[]>([])
const users = ref<UserRow[]>([])
const loading = ref(false)
const dialogVisible = ref(false)
const saving = ref(false)
const deletingId = ref<number | null>(null)
const editing = ref<TeamRow | null>(null)

const form = ref({
  name: '',
  captain_id: undefined as number | undefined,
  member_ids: [] as number[],
})

function openCreate() {
  editing.value = null
  form.value = { name: '', captain_id: undefined, member_ids: [] }
  dialogVisible.value = true
}

function openEdit(row: TeamRow) {
  editing.value = row
  form.value = {
    name: row.name,
    captain_id: row.captain_id,
    member_ids: row.members.map((m) => m.user_id),
  }
  dialogVisible.value = true
}

async function loadTeams() {
  loading.value = true
  try {
    const { data } = await http.get<TeamRow[]>('/admin/teams')
    teams.value = data
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || '加载团队失败')
  } finally {
    loading.value = false
  }
}

async function loadUsers() {
  try {
    const { data } = await http.get<UserRow[]>('/admin/users')
    users.value = data
  } catch {
    users.value = []
  }
}

async function onSave() {
  if (form.value.name.trim().length < 2 || form.value.name.trim().length > 20) {
    ElMessage.warning('团队名需为 2-20 个字符')
    return
  }
  if (!form.value.captain_id) {
    ElMessage.warning('请选择队长')
    return
  }
  if (form.value.member_ids.length < 1 || form.value.member_ids.length > 3) {
    ElMessage.warning('成员需为 1-3 人（含队长）')
    return
  }
  if (!form.value.member_ids.includes(form.value.captain_id)) {
    ElMessage.warning('队长必须包含在成员名单中')
    return
  }
  saving.value = true
  try {
    if (editing.value) {
      await http.patch(`/admin/teams/${editing.value.id}`, {
        name: form.value.name.trim(),
        captain_id: form.value.captain_id,
        member_ids: form.value.member_ids,
      })
      ElMessage.success('团队已更新')
    } else {
      await http.post('/admin/teams', {
        name: form.value.name.trim(),
        captain_id: form.value.captain_id,
        member_ids: form.value.member_ids,
      })
      ElMessage.success('团队已创建')
    }
    dialogVisible.value = false
    await loadTeams()
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || '保存失败')
  } finally {
    saving.value = false
  }
}

async function onDelete(row: TeamRow) {
  try {
    await ElMessageBox.confirm(
      `确定要删除团队「${row.name}」吗？已有报名的团队无法删除。`,
      '删除确认',
      { type: 'warning', confirmButtonText: '删除', cancelButtonText: '取消' },
    )
  } catch {
    return
  }
  deletingId.value = row.id
  try {
    await http.delete(`/admin/teams/${row.id}`)
    ElMessage.success('团队已删除')
    await loadTeams()
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || '删除失败')
  } finally {
    deletingId.value = null
  }
}

onMounted(() => {
  loadTeams()
  loadUsers()
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
.member-chip {
  display: inline-block;
  margin: 2px 4px 2px 0;
  padding: 2px 8px;
  border-radius: 4px;
  background: #f0f2f5;
  color: #303133;
  font-size: 12px;
}
.form-tip {
  color: #909399;
  font-size: 12px;
  margin-top: -8px;
}
</style>
