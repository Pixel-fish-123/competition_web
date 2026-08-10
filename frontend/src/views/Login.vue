<template>
  <div class="login-page">
    <el-card class="login-card">
      <el-tabs v-model="activeTab">
        <el-tab-pane label="登录" name="login">
          <el-form
            ref="loginFormRef"
            :model="loginForm"
            :rules="loginRules"
            label-position="top"
            @submit.prevent
          >
            <el-form-item label="用户名" prop="username">
              <el-input
                v-model="loginForm.username"
                placeholder="请输入用户名"
                autocomplete="username"
              />
            </el-form-item>
            <el-form-item label="密码" prop="password">
              <el-input
                v-model="loginForm.password"
                type="password"
                placeholder="请输入密码"
                autocomplete="current-password"
                show-password
                @keyup.enter="handleLogin"
              />
            </el-form-item>
            <el-button
              type="primary"
              class="submit-btn"
              :loading="submitting"
              @click="handleLogin"
            >
              登录
            </el-button>
          </el-form>
        </el-tab-pane>

        <el-tab-pane label="注册" name="register">
          <el-form
            ref="registerFormRef"
            :model="registerForm"
            :rules="registerRules"
            label-position="top"
            @submit.prevent
          >
            <el-form-item label="用户名" prop="username">
              <el-input
                v-model="registerForm.username"
                placeholder="2-30 个字符"
                autocomplete="username"
              />
            </el-form-item>
            <el-form-item label="昵称（选填）" prop="nickname">
              <el-input
                v-model="registerForm.nickname"
                placeholder="参赛展示用昵称，2-30 个字符"
              />
            </el-form-item>
            <el-form-item label="QQ（选填）" prop="qq">
              <el-input
                v-model="registerForm.qq"
                placeholder="机器人 @ 选手用，仅数字"
                maxlength="20"
              />
            </el-form-item>
            <el-form-item label="邮箱" prop="email">
              <el-input
                v-model="registerForm.email"
                placeholder="请输入邮箱"
                autocomplete="email"
              />
            </el-form-item>
            <el-form-item label="密码" prop="password">
              <el-input
                v-model="registerForm.password"
                type="password"
                placeholder="至少 6 位"
                autocomplete="new-password"
                show-password
              />
            </el-form-item>
            <el-form-item label="确认密码" prop="confirm">
              <el-input
                v-model="registerForm.confirm"
                type="password"
                placeholder="请再次输入密码"
                autocomplete="new-password"
                show-password
                @keyup.enter="handleRegister"
              />
            </el-form-item>
            <el-button
              type="primary"
              class="submit-btn"
              :loading="submitting"
              @click="handleRegister"
            >
              注册
            </el-button>
          </el-form>
        </el-tab-pane>
      </el-tabs>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, type FormInstance, type FormRules } from 'element-plus'
import { useAuthStore } from '../stores/auth'

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()

const activeTab = ref<'login' | 'register'>('login')
const submitting = ref(false)

const loginFormRef = ref<FormInstance>()
const registerFormRef = ref<FormInstance>()

const loginForm = reactive({
  username: '',
  password: '',
})

const registerForm = reactive({
  username: '',
  nickname: '',
  qq: '',
  email: '',
  password: '',
  confirm: '',
})

const loginRules: FormRules = {
  username: [{ required: true, message: '请输入用户名', trigger: 'blur' }],
  password: [{ required: true, message: '请输入密码', trigger: 'blur' }],
}

const registerRules: FormRules = {
  username: [
    { required: true, message: '请输入用户名', trigger: 'blur' },
    { min: 2, max: 30, message: '用户名需为 2-30 个字符', trigger: 'blur' },
  ],
  nickname: [
    {
      validator: (_rule, value: string, callback) => {
        if (value && (value.length < 2 || value.length > 30)) {
          callback(new Error('昵称需为 2-30 个字符'))
        } else {
          callback()
        }
      },
      trigger: 'blur',
    },
  ],
  qq: [
    {
      validator: (_rule, value: string, callback) => {
        if (value && !/^\d+$/.test(value)) {
          callback(new Error('QQ 号应为纯数字'))
        } else {
          callback()
        }
      },
      trigger: 'blur',
    },
  ],
  email: [
    { required: true, message: '请输入邮箱', trigger: 'blur' },
    { type: 'email', message: '邮箱格式不正确', trigger: 'blur' },
  ],
  password: [
    { required: true, message: '请输入密码', trigger: 'blur' },
    { min: 6, message: '密码至少 6 位', trigger: 'blur' },
  ],
  confirm: [
    { required: true, message: '请再次输入密码', trigger: 'blur' },
    {
      validator: (_rule, value: string, callback) => {
        if (value !== registerForm.password) {
          callback(new Error('两次输入的密码不一致'))
        } else {
          callback()
        }
      },
      trigger: 'blur',
    },
  ],
}

function handleAuthError(err: unknown) {
  const status = (err as { response?: { status?: number; data?: { detail?: string } } })
    ?.response?.status
  const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data
    ?.detail
  switch (status) {
    case 401:
      ElMessage.error('用户名或密码错误')
      break
    case 423:
      ElMessage.error('账号已锁定，请稍后再试')
      break
    case 429:
      ElMessage.error('请求过于频繁')
      break
    case 400:
    case 422:
      ElMessage.error(detail || '注册信息校验失败')
      break
    default:
      ElMessage.error(detail || '操作失败，请稍后再试')
  }
}

function redirectAfterAuth() {
  const redirect = typeof route.query.redirect === 'string' ? route.query.redirect : '/'
  router.push(redirect)
}

async function handleLogin() {
  if (!loginFormRef.value) return
  const valid = await loginFormRef.value.validate().catch(() => false)
  if (!valid) return
  submitting.value = true
  try {
    await auth.login(loginForm.username, loginForm.password)
    ElMessage.success('登录成功')
    redirectAfterAuth()
  } catch (err) {
    handleAuthError(err)
  } finally {
    submitting.value = false
  }
}

async function handleRegister() {
  if (!registerFormRef.value) return
  const valid = await registerFormRef.value.validate().catch(() => false)
  if (!valid) return
  submitting.value = true
  try {
    await auth.register(
      registerForm.username,
      registerForm.email,
      registerForm.password,
      registerForm.nickname.trim() || undefined,
      registerForm.qq.trim() || undefined,
    )
    ElMessage.success('注册成功，已自动登录')
    redirectAfterAuth()
  } catch (err) {
    handleAuthError(err)
  } finally {
    submitting.value = false
  }
}
</script>

<style scoped>
.login-page {
  display: flex;
  justify-content: center;
  padding-top: 48px;
}
.login-card {
  width: 400px;
}
.submit-btn {
  width: 100%;
  margin-top: 8px;
}
</style>
