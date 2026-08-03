<template>
  <div class="admin-page">
    <h2>积分管理</h2>

    <el-card class="grant-card" shadow="never">
      <template #header>发放积分</template>
      <el-form label-width="90px" inline>
        <el-form-item label="用户">
          <el-select
            v-model="grant.user_id"
            filterable
            placeholder="搜索并选择用户"
            style="width: 220px"
          >
            <el-option
              v-for="u in users"
              :key="u.id"
              :label="`${u.username} (#${u.id})`"
              :value="u.id"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="分值">
          <el-input-number v-model="grant.amount" :min="1" :step="1" />
        </el-form-item>
        <el-form-item label="原因">
          <el-input v-model="grant.reason" placeholder="发放原因" style="width: 200px" />
        </el-form-item>
        <el-form-item>
          <el-button type="primary" :loading="granting" @click="doGrant">发放</el-button>
        </el-form-item>
      </el-form>
    </el-card>

    <el-card shadow="never">
      <template #header>
        <div class="card-head">
          <span>积分排行榜（Top 20）</span>
          <el-button size="small" @click="loadLeaderboard">刷新</el-button>
        </div>
      </template>
      <el-table :data="leaderboard" v-loading="lbLoading" border stripe>
        <el-table-column type="index" label="#" width="60" />
        <el-table-column prop="username" label="用户名" min-width="140" />
        <el-table-column prop="total" label="总分" width="100" />
      </el-table>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import http from '../../api/http'

interface UserRow {
  id: number
  username: string
}
interface LeaderboardRow {
  user_id: number
  username: string
  total: number
}

const users = ref<UserRow[]>([])
const leaderboard = ref<LeaderboardRow[]>([])
const lbLoading = ref(false)
const granting = ref(false)

const grant = reactive({
  user_id: undefined as number | undefined,
  amount: 1,
  kind: 'manual',
  reason: '',
})

async function loadUsers() {
  try {
    const { data } = await http.get<UserRow[]>('/admin/users')
    users.value = data
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || '加载用户失败')
  }
}

async function loadLeaderboard() {
  lbLoading.value = true
  try {
    const { data } = await http.get<LeaderboardRow[]>('/points/leaderboard')
    leaderboard.value = data.slice(0, 20)
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || '加载排行榜失败')
  } finally {
    lbLoading.value = false
  }
}

async function doGrant() {
  if (!grant.user_id) {
    ElMessage.warning('请选择用户')
    return
  }
  if (grant.reason.trim().length < 2) {
    ElMessage.warning('原因至少 2 个字符')
    return
  }
  granting.value = true
  try {
    await http.post('/admin/points', {
      user_id: grant.user_id,
      amount: grant.amount,
      kind: grant.kind,
      reason: grant.reason.trim(),
    })
    ElMessage.success('积分已发放')
    grant.reason = ''
    loadLeaderboard()
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || '发放失败')
  } finally {
    granting.value = false
  }
}

onMounted(() => {
  loadUsers()
  loadLeaderboard()
})
</script>

<style scoped>
.admin-page h2 {
  margin-top: 0;
}
.grant-card {
  margin-bottom: 16px;
}
.card-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
</style>
