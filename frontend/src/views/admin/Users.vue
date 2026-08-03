<template>
  <div class="admin-page">
    <h2>选手管理</h2>
    <div class="toolbar">
      <el-input
        v-model="search"
        placeholder="按用户名搜索"
        clearable
        style="width: 200px"
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
      <el-select
        v-model="statusFilter"
        placeholder="状态筛选"
        clearable
        style="width: 140px"
      >
        <el-option label="全部" value="" />
        <el-option label="正常" value="active" />
        <el-option label="封禁" value="banned" />
      </el-select>
      <el-button type="primary" @click="loadUsers">刷新</el-button>
    </div>

    <el-table :data="filteredUsers" v-loading="loading" border stripe>
      <el-table-column prop="id" label="ID" width="70" />
      <el-table-column prop="username" label="用户名" min-width="120" />
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
      <el-table-column label="状态" width="120">
        <template #default="{ row }">
          <el-switch
            :model-value="row.status === 'active'"
            active-text="正常"
            inactive-text="封禁"
            @change="(v: boolean) => toggleStatus(row, v)"
          />
        </template>
      </el-table-column>
      <el-table-column prop="created_at" label="注册时间" min-width="170" />
      <el-table-column label="操作" width="120">
        <template #default="{ row }">
          <el-button size="small" @click="openReset(row)">重置密码</el-button>
        </template>
      </el-table-column>
    </el-table>

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

    <el-dialog v-model="banVisible" title="封禁确认" width="420px">
      <p>确定要封禁用户 <b>{{ banTarget?.username }}</b> 吗？封禁后该用户将无法登录。</p>
      <template #footer>
        <el-button @click="banVisible = false">取消</el-button>
        <el-button type="danger" :loading="banning" @click="confirmBan">确认封禁</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import http from '../../api/http'

interface UserRow {
  id: number
  username: string
  email: string
  role: string
  status: string
  created_at: string
}

const users = ref<UserRow[]>([])
const loading = ref(false)
const search = ref('')
const roleFilter = ref('')
const statusFilter = ref('')

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
    if (q && !u.username.toLowerCase().includes(q)) return false
    if (roleFilter.value && u.role !== roleFilter.value) return false
    if (statusFilter.value && u.status !== statusFilter.value) return false
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

const banVisible = ref(false)
const banTarget = ref<UserRow | null>(null)
const banning = ref(false)

function toggleStatus(row: UserRow, active: boolean) {
  if (active) {
    // 解封：直接执行
    setStatus(row, 'active')
  } else {
    // 封禁：先确认
    banTarget.value = row
    banVisible.value = true
  }
}

async function confirmBan() {
  if (!banTarget.value) return
  banning.value = true
  try {
    await setStatus(banTarget.value, 'banned')
    banVisible.value = false
  } finally {
    banning.value = false
  }
}

async function setStatus(row: UserRow, status: string) {
  try {
    await http.patch<UserRow>(`/admin/users/${row.id}`, { status })
    ElMessage.success(status === 'active' ? '已解封' : '已封禁')
    loadUsers()
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || '更新状态失败')
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
.dialog-tip {
  color: #909399;
  font-size: 12px;
  margin-top: -8px;
  margin-bottom: 8px;
}
</style>
