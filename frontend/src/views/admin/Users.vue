<template>
  <div class="admin-page">
    <h2>选手管理</h2>
    <div class="toolbar">
      <el-input
        v-model="search"
        placeholder="按用户名或昵称搜索"
        clearable
        style="width: 220px"
        @input="loadUsers"
      />
      <el-select
        v-model="roleFilter"
        placeholder="角色筛选"
        clearable
        style="width: 140px"
      >
        <el-option label="全部" value="" />
        <el-option label="管理员" value="admin" />
        <el-option label="裁判" value="referee" />
        <el-option label="选手" value="player" />
      </el-select>
      <el-button type="primary" @click="loadUsers">刷新</el-button>
      <el-button type="success" @click="openCreate">创建用户</el-button>
    </div>

    <el-table :data="filteredUsers" v-loading="loading" border stripe>
      <el-table-column prop="username" label="用户名" min-width="120" />
      <el-table-column label="昵称" min-width="120">
        <template #default="{ row }">
          <span v-if="row.nickname">{{ row.nickname }}</span>
          <span v-else class="nickname-empty">—</span>
        </template>
      </el-table-column>
      <el-table-column prop="email" label="邮箱" min-width="180" />
      <el-table-column label="角色" width="150">
        <template #default="{ row }">
          <el-select
            :model-value="row.role"
            size="small"
            @change="(v: string) => changeRole(row, v)"
          >
            <el-option label="管理员" value="admin" />
            <el-option label="裁判" value="referee" />
            <el-option label="选手" value="player" />
          </el-select>
          <el-tag
            :type="roleTagType(row.role)"
            size="small"
            effect="light"
            class="role-tag"
          >
            {{ roleLabel(row.role) }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="created_at" label="注册时间" min-width="170" />
      <el-table-column label="操作" width="200">
        <template #default="{ row }">
          <el-button size="small" @click="openReset(row)">重置密码</el-button>
          <el-button
            size="small"
            type="danger"
            :loading="deletingId === row.id"
            @click="openDelete(row)"
          >
            删除
          </el-button>
        </template>
      </el-table-column>
    </el-table>

    <el-dialog v-model="createVisible" title="创建用户" width="460px">
      <el-form label-width="80px">
        <el-form-item label="用户名">
          <el-input v-model="createForm.username" placeholder="2-30 个字符" />
        </el-form-item>
        <el-form-item label="邮箱">
          <el-input v-model="createForm.email" placeholder="name@example.com" />
        </el-form-item>
        <el-form-item label="密码">
          <el-input v-model="createForm.password" type="password" show-password placeholder="至少 6 位" />
        </el-form-item>
        <el-form-item label="角色">
          <el-select v-model="createForm.role" placeholder="选择角色" style="width: 100%">
            <el-option label="管理员" value="admin" />
            <el-option label="裁判" value="referee" />
            <el-option label="选手" value="player" />
          </el-select>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="createVisible = false">取消</el-button>
        <el-button type="primary" :loading="creating" @click="doCreate">确认创建</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="resetVisible" title="重置密码" width="420px">
      <el-form label-width="90px">
        <el-form-item label="用户">
          <span>{{ resetTarget?.username }}</span>
        </el-form-item>
        <el-form-item label="新密码">
          <el-input v-model="newPassword" type="password" show-password />
        </el-form-item>
      </el-form>
      <div class="dialog-tip">密码至少 6 位</div>
      <template #footer>
        <el-button @click="resetVisible = false">取消</el-button>
        <el-button type="primary" :loading="resetting" @click="doReset">确认</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import http from '../../api/http'

interface UserRow {
  id: number
  username: string
  nickname: string | null
  email: string
  role: string
  status: string
  created_at: string
}

const users = ref<UserRow[]>([])
const loading = ref(false)
const search = ref('')
const roleFilter = ref('')

const createVisible = ref(false)
const creating = ref(false)
const createForm = ref({ username: '', email: '', password: '', role: '' })
const deletingId = ref<number | null>(null)

const ROLE_LABELS: Record<string, string> = {
  admin: '管理员',
  referee: '裁判',
  player: '选手',
}
const ROLE_TAGS: Record<string, 'danger' | 'warning' | 'info'> = {
  admin: 'danger',
  referee: 'warning',
  player: 'info',
}

function roleLabel(role: string): string {
  return ROLE_LABELS[role] ?? role
}
function roleTagType(role: string): 'danger' | 'warning' | 'info' {
  return ROLE_TAGS[role] ?? 'info'
}

const filteredUsers = computed(() => {
  const q = search.value.trim().toLowerCase()
  return users.value.filter((u) => {
    if (q) {
      const nickname = (u.nickname || '').toLowerCase()
      if (!u.username.toLowerCase().includes(q) && !nickname.includes(q)) return false
    }
    if (roleFilter.value && u.role !== roleFilter.value) return false
    return true
  })
})

async function loadUsers() {
  loading.value = true
  try {
    const { data } = await http.get<UserRow[]>('/admin/users')
    users.value = data
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || '加载用户失败')
  } finally {
    loading.value = false
  }
}

async function changeRole(row: UserRow, role: string) {
  if (role === row.role) return
  try {
    await http.patch<UserRow>(`/admin/users/${row.id}`, { role })
    ElMessage.success('角色已更新')
    loadUsers()
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || '更新角色失败')
    loadUsers()
  }
}

const resetVisible = ref(false)
const resetTarget = ref<UserRow | null>(null)
const newPassword = ref('')
const resetting = ref(false)

function openReset(row: UserRow) {
  resetTarget.value = row
  newPassword.value = ''
  resetVisible.value = true
}

async function doReset() {
  if (!resetTarget.value || newPassword.value.length < 6) {
    ElMessage.warning('密码至少 6 位')
    return
  }
  resetting.value = true
  try {
    await http.patch(`/admin/users/${resetTarget.value.id}`, {
      password: newPassword.value,
    })
    ElMessage.success('密码已重置')
    resetVisible.value = false
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || '重置密码失败')
  } finally {
    resetting.value = false
  }
}

function openCreate() {
  createForm.value = { username: '', email: '', password: '', role: 'player' }
  createVisible.value = true
}

async function doCreate() {
  const f = createForm.value
  if (f.username.trim().length < 2 || f.username.trim().length > 30) {
    ElMessage.warning('用户名需为 2-30 个字符')
    return
  }
  if (!/.+@.+\..+/.test(f.email.trim())) {
    ElMessage.warning('邮箱格式不正确')
    return
  }
  if (f.password.length < 6) {
    ElMessage.warning('密码至少 6 位')
    return
  }
  if (!f.role) {
    ElMessage.warning('请选择角色')
    return
  }
  creating.value = true
  try {
    await http.post('/admin/users', {
      username: f.username.trim(),
      email: f.email.trim(),
      password: f.password,
      role: f.role,
    })
    ElMessage.success('用户已创建')
    createVisible.value = false
    loadUsers()
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || '创建用户失败')
  } finally {
    creating.value = false
  }
}

async function openDelete(row: UserRow) {
  try {
    await ElMessageBox.confirm(
      `确定要删除用户「${row.username}」吗？该用户的所有报名/队伍/积分记录将被清理且不可恢复；其未完结对局将判对手获胜（按轮空计算）。`,
      '删除确认',
      { type: 'warning', confirmButtonText: '删除', cancelButtonText: '取消' }
    )
  } catch {
    return
  }
  deletingId.value = row.id
  try {
    await http.delete(`/admin/users/${row.id}`)
    ElMessage.success('用户已删除')
    loadUsers()
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || '删除用户失败')
    loadUsers()
  } finally {
    deletingId.value = null
  }
}

onMounted(loadUsers)
</script>

<style scoped>
.admin-page h2 {
  margin-top: 0;
}
.toolbar {
  display: flex;
  gap: 12px;
  margin-bottom: 16px;
}
.role-tag {
  margin-left: 8px;
}
.nickname-empty {
  color: #c0c4cc;
}
.dialog-tip {
  color: #909399;
  font-size: 12px;
  margin-top: -8px;
  margin-bottom: 8px;
}
</style>
