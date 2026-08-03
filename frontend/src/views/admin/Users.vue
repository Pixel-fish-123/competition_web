<template>
  <div class="admin-page">
    <h2>选手管理</h2>
    <div class="toolbar">
      <el-input
        v-model="search"
        placeholder="按用户名搜索"
        clearable
        style="width: 240px"
        @input="loadUsers"
      />
      <el-button type="primary" @click="loadUsers">刷新</el-button>
    </div>

    <el-table :data="filteredUsers" v-loading="loading" border stripe>
      <el-table-column prop="id" label="ID" width="70" />
      <el-table-column prop="username" label="用户名" min-width="120" />
      <el-table-column prop="email" label="邮箱" min-width="180" />
      <el-table-column label="角色" width="140">
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
      <template #footer>
        <el-button @click="resetVisible = false">取消</el-button>
        <el-button type="primary" :loading="resetting" @click="doReset">确认</el-button>
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

const filteredUsers = computed(() => {
  const q = search.value.trim().toLowerCase()
  if (!q) return users.value
  return users.value.filter((u) => u.username.toLowerCase().includes(q))
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
  try {
    const { data } = await http.patch<UserRow>(`/admin/users/${row.id}`, { role })
    row.role = data.role
    ElMessage.success('角色已更新')
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || '更新角色失败')
    loadUsers()
  }
}

async function toggleStatus(row: UserRow, active: boolean) {
  const status = active ? 'active' : 'banned'
  try {
    const { data } = await http.patch<UserRow>(`/admin/users/${row.id}`, { status })
    row.status = data.status
    ElMessage.success('状态已更新')
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
</style>
