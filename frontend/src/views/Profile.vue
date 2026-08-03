<template>
  <div class="profile" v-loading="loading">
    <el-empty v-if="!loading && !auth.user" description="请先登录" />

    <template v-if="auth.user">
      <!-- 用户信息 -->
      <section class="profile__section">
        <div class="profile__head">
          <h2>我的信息</h2>
          <el-button size="small" @click="openNicknameDialog">修改昵称</el-button>
        </div>
        <el-descriptions :column="2" border>
          <el-descriptions-item label="用户名">{{ auth.user.username }}</el-descriptions-item>
          <el-descriptions-item label="昵称">{{ auth.user.nickname || auth.user.username }}</el-descriptions-item>
          <el-descriptions-item label="邮箱">{{ auth.user.email }}</el-descriptions-item>
          <el-descriptions-item label="角色">{{ roleLabel(auth.user.role) }}</el-descriptions-item>
          <el-descriptions-item label="状态">{{ statusLabel(auth.user.status) }}</el-descriptions-item>
        </el-descriptions>
      </section>

      <!-- 我的队伍 -->
      <section class="profile__section">
        <div class="profile__head">
          <h2>我的队伍</h2>
          <el-button v-if="!myTeam" type="primary" size="small" @click="dialogVisible = true">
            建队
          </el-button>
        </div>
        <el-card v-if="myTeam" class="team-card">
          <div class="team-card__head">
            <div class="team-card__row">
              <span class="team-card__name">{{ myTeam.name }}</span>
              <el-tag size="small" type="success">队长</el-tag>
            </div>
            <el-button
              v-if="isCaptain"
              type="primary"
              size="small"
              @click="inviteDialogVisible = true"
            >
              添加成员
            </el-button>
          </div>
          <div class="team-card__meta">
            <span>成员数：{{ myTeam.members.length }}</span>
            <span v-if="myTeam.captain_name">队长：{{ myTeam.captain_name }}</span>
          </div>
          <ul class="team-card__members">
            <li v-for="m in myTeam.members" :key="m.id" class="team-card__member">
              <span>{{ m.nickname || m.username }}</span>
              <el-button
                v-if="isCaptain && m.user_id !== auth.user?.id"
                type="danger"
                text
                size="small"
                @click="removeMember(m)"
              >
                移除
              </el-button>
            </li>
          </ul>
        </el-card>
        <el-empty v-else description="暂无队伍" :image-size="60" />
      </section>

      <!-- 我的报名 -->
      <section class="profile__section">
        <h2>我的报名</h2>
        <el-table :data="myRegistrations" v-loading="regLoading" border stripe>
          <el-table-column label="比赛" min-width="160">
            <template #default="{ row }">
              {{ competitionName(row.competition_id) }}
            </template>
          </el-table-column>
          <el-table-column label="参赛形式" width="110">
            <template #default="{ row }">
              {{ participantLabel(row.participant_type) }}
            </template>
          </el-table-column>
          <el-table-column prop="status" label="状态" width="110">
            <template #default="{ row }">
              <el-tag size="small">{{ regStatusLabel(row.status) }}</el-tag>
            </template>
          </el-table-column>
        </el-table>
      </section>

      <!-- 积分流水 -->
      <section class="profile__section">
        <h2>积分</h2>
        <div class="profile__balance">
          当前余额：<span class="profile__balance-num">{{ points.balance ?? 0 }}</span>
        </div>
        <el-table :data="points.transactions" v-loading="pointsLoading" border stripe>
          <el-table-column label="变动" width="90">
            <template #default="{ row }">
              <span :class="row.amount >= 0 ? 'amount-plus' : 'amount-minus'">
                {{ row.amount >= 0 ? '+' : '' }}{{ row.amount }}
              </span>
            </template>
          </el-table-column>
          <el-table-column label="类型" width="120">
            <template #default="{ row }">
              <el-tag size="small">{{ kindLabel(row.kind) }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="reason" label="说明" min-width="160" />
          <el-table-column label="时间" width="180">
            <template #default="{ row }">
              {{ formatTime(row.created_at) }}
            </template>
          </el-table-column>
        </el-table>
      </section>
    </template>

    <!-- 建队对话框 -->
    <el-dialog v-model="dialogVisible" title="创建队伍" width="420px">
      <el-form label-width="80px" @submit.prevent>
        <el-form-item label="队伍名称" required>
          <el-input v-model="teamName" placeholder="请输入队伍名称" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="creating" @click="createTeam">创建</el-button>
      </template>
    </el-dialog>

    <!-- 修改昵称对话框 -->
    <el-dialog v-model="nicknameDialogVisible" title="修改昵称" width="420px">
      <el-form label-width="80px" @submit.prevent>
        <el-form-item label="昵称" required>
          <el-input
            v-model="newNickname"
            placeholder="参赛展示用昵称"
            maxlength="30"
            @keyup.enter="saveNickname"
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="nicknameDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="savingNickname" @click="saveNickname">确定</el-button>
      </template>
    </el-dialog>

    <!-- 添加成员对话框 -->
    <el-dialog v-model="inviteDialogVisible" title="添加成员" width="420px">
      <el-form label-width="80px" @submit.prevent>
        <el-form-item label="用户名" required>
          <el-input
            v-model="inviteUsername"
            placeholder="请输入对方用户名"
            @keyup.enter="inviteMember"
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="inviteDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="inviting" @click="inviteMember">确定</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import http from '../api/http'
import { useAuthStore } from '../stores/auth'

interface TeamMember {
  id: number
  user_id: number
  username: string
  nickname: string | null
}

interface TeamInfo {
  id: number
  name: string
  captain_id?: number
  captain_name?: string
  members: TeamMember[]
}

interface Registration {
  id: number
  competition_id: number
  participant_type: string
  status: string
}

interface MyRegistrationsResp {
  registrations: Registration[]
}

interface PointTx {
  id: number
  amount: number
  kind: string
  reason: string | null
  created_at: string
}

interface PointsData {
  balance: number
  transactions: PointTx[]
}

interface Competition {
  id: number
  name: string
}

const auth = useAuthStore()
const loading = ref(false)
const myTeam = ref<TeamInfo | null>(null)
const myRegistrations = ref<Registration[]>([])
const regLoading = ref(false)
const points = ref<PointsData>({ balance: 0, transactions: [] })
const pointsLoading = ref(false)
const competitions = ref<Competition[]>([])
const dialogVisible = ref(false)
const teamName = ref('')
const creating = ref(false)
const nicknameDialogVisible = ref(false)
const newNickname = ref('')
const savingNickname = ref(false)
const inviteDialogVisible = ref(false)
const inviteUsername = ref('')
const inviting = ref(false)

const isCaptain = computed(
  () => myTeam.value?.captain_id === auth.user?.id,
)

function roleLabel(r: string) {
  if (r === 'admin') return '管理员'
  if (r === 'referee') return '裁判'
  if (r === 'player') return '选手'
  return r
}
function statusLabel(s: string) {
  if (s === 'active') return '正常'
  if (s === 'banned') return '封禁'
  return s
}
function participantLabel(t: string) {
  if (t === 'team') return '团队赛'
  if (t === 'individual') return '个人赛'
  if (t === 'mixed') return '混合赛'
  return t
}
function regStatusLabel(s: string) {
  if (s === 'pending') return '待审核'
  if (s === 'approved') return '已通过'
  if (s === 'rejected') return '已拒绝'
  return s
}
function kindLabel(k: string) {
  if (k === 'match_win') return '比赛获胜'
  if (k === 'match_participation') return '参赛奖励'
  if (k === 'admin_adjust') return '管理员调整'
  if (k === 'registration') return '报名'
  return k
}
function formatTime(t: string) {
  return new Date(t).toLocaleString('zh-CN')
}
function competitionName(id: number) {
  const c = competitions.value.find((x) => x.id === id)
  return c ? c.name : `比赛#${id}`
}

async function loadMyTeam() {
  try {
    const { data } = await http.get<{ team: TeamInfo | null }>('/teams/my')
    myTeam.value = data.team
    if (myTeam.value && !Array.isArray(myTeam.value.members)) {
      myTeam.value.members = []
    }
  } catch {
    myTeam.value = null
  }
}

async function loadMyRegistrations() {
  regLoading.value = true
  try {
    const { data } = await http.get<MyRegistrationsResp>('/my/registrations')
    myRegistrations.value = data.registrations
  } catch {
    myRegistrations.value = []
  } finally {
    regLoading.value = false
  }
}

async function loadPoints() {
  pointsLoading.value = true
  try {
    const { data } = await http.get<PointsData>('/points/me')
    points.value = data
  } catch {
    points.value = { balance: 0, transactions: [] }
  } finally {
    pointsLoading.value = false
  }
}

async function loadCompetitions() {
  try {
    const { data } = await http.get<Competition[]>('/competitions')
    competitions.value = data
  } catch {
    competitions.value = []
  }
}

async function createTeam() {
  if (teamName.value.trim().length < 2) {
    ElMessage.warning('队伍名称至少 2 个字符')
    return
  }
  creating.value = true
  try {
    await http.post('/teams', { name: teamName.value.trim() })
    ElMessage.success('队伍创建成功')
    dialogVisible.value = false
    teamName.value = ''
    await loadMyTeam()
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || '创建失败')
  } finally {
    creating.value = false
  }
}

function openNicknameDialog() {
  newNickname.value = auth.user?.nickname || ''
  nicknameDialogVisible.value = true
}

async function saveNickname() {
  const nickname = newNickname.value.trim()
  if (!nickname) {
    ElMessage.warning('昵称不能为空')
    return
  }
  savingNickname.value = true
  try {
    await auth.updateNickname(nickname)
    ElMessage.success('昵称已更新')
    nicknameDialogVisible.value = false
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || '昵称修改失败')
  } finally {
    savingNickname.value = false
  }
}

async function inviteMember() {
  const username = inviteUsername.value.trim()
  if (!username) {
    ElMessage.warning('请输入对方用户名')
    return
  }
  if (!myTeam.value) return
  inviting.value = true
  try {
    await http.post(`/teams/${myTeam.value.id}/members`, { username })
    ElMessage.success('已邀请成员')
    inviteDialogVisible.value = false
    inviteUsername.value = ''
    await loadMyTeam()
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || '添加成员失败')
  } finally {
    inviting.value = false
  }
}

async function removeMember(member: TeamMember) {
  if (!myTeam.value) return
  try {
    await ElMessageBox.confirm(
      `确定将成员「${member.nickname || member.username}」移出队伍吗？`,
      '移除成员',
      { type: 'warning', confirmButtonText: '移除', cancelButtonText: '取消' },
    )
  } catch {
    return
  }
  try {
    await http.delete(`/teams/${myTeam.value.id}/members/${member.user_id}`)
    ElMessage.success('成员已移除')
    await loadMyTeam()
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || '移除成员失败')
  }
}

onMounted(async () => {
  loading.value = true
  await auth.fetchMe()
  if (auth.user) {
    await Promise.all([
      loadMyTeam(),
      loadMyRegistrations(),
      loadPoints(),
      loadCompetitions(),
    ])
  }
  loading.value = false
})
</script>

<style scoped>
.profile {
  max-width: 1100px;
  margin: 0 auto;
  min-height: 300px;
}
.profile__section {
  margin-bottom: 32px;
}
.profile__section h2 {
  font-size: 20px;
  margin: 0 0 12px;
  border-left: 4px solid #409eff;
  padding-left: 10px;
}
.profile__head {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.profile__head h2 {
  margin-bottom: 12px;
}
.team-card__head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}
.team-card__row {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
}
.team-card__name {
  font-size: 18px;
  font-weight: 600;
}
.team-card__meta {
  display: flex;
  gap: 16px;
  color: #909399;
  font-size: 13px;
  margin-bottom: 8px;
}
.team-card__members {
  list-style: none;
  margin: 0;
  padding: 0;
  border-top: 1px solid #ebeef5;
}
.team-card__member {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 8px 4px;
  font-size: 14px;
  border-bottom: 1px solid #f5f7fa;
}
.profile__balance {
  margin-bottom: 12px;
  font-size: 15px;
}
.profile__balance-num {
  font-size: 22px;
  font-weight: 700;
  color: #e6a23c;
}
.amount-plus {
  color: #67c23a;
  font-weight: 600;
}
.amount-minus {
  color: #f56c6c;
  font-weight: 600;
}
</style>
