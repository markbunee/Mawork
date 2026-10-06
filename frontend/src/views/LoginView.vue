<script setup lang="ts">
import { ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { login, applyMember } from '@/api/auth'

const router = useRouter()
const route = useRoute()

type Mode = 'login' | 'apply'
const mode = ref<Mode>('login')

const username = ref('')
const password = ref('')
const phone = ref('')
const loading = ref(false)

const isApply = ref(false)
function switchMode(next: Mode) {
  mode.value = next
  isApply.value = next === 'apply'
  phone.value = ''
  password.value = ''
}

async function onSubmit() {
  const name = username.value.trim()
  if (!name || !password.value) {
    ElMessage.warning('请输入用户名和密码')
    return
  }
  loading.value = true
  try {
    if (mode.value === 'login') {
      await login(name, password.value)
      const redirect = (route.query.redirect as string) || '/home'
      router.replace(redirect)
      return
    }
    // 申请模式：用户名 + 手机号 + 密码
    if (!phone.value.trim()) {
      ElMessage.warning('请输入手机号')
      return
    }
    const res = await applyMember({
      username: name,
      phone: phone.value.trim(),
      password: password.value,
    })
    ElMessage.success(res.message || '已提交申请')
    switchMode('login')
  } catch (e) {
    ElMessage.error(e instanceof Error ? e.message : '操作失败')
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <div class="login-page">
    <form class="login-card" @submit.prevent="onSubmit">
      <div class="login-brand">
        <span class="brand-mark">Ma</span>
        <span class="brand-text">Work</span>
      </div>
      <p class="login-sub">{{ mode === 'login' ? '个人工作操作系统' : '成员申请 / 重置密码' }}</p>

      <label class="login-field">
        <span class="login-label">用户名</span>
        <input
          v-model="username"
          class="login-input"
          type="text"
          autocomplete="username"
          placeholder="请输入用户名"
        />
      </label>

      <label v-if="mode === 'apply'" class="login-field">
        <span class="login-label">手机号</span>
        <input
          v-model="phone"
          class="login-input"
          type="tel"
          inputmode="numeric"
          autocomplete="tel"
          placeholder="请输入手机号"
        />
      </label>

      <label class="login-field">
        <span class="login-label">{{ mode === 'apply' ? '新密码' : '密码' }}</span>
        <input
          v-model="password"
          class="login-input"
          type="password"
          :autocomplete="mode === 'apply' ? 'new-password' : 'current-password'"
          :placeholder="mode === 'apply' ? '至少 8 位' : '请输入密码'"
        />
      </label>

      <button class="login-btn" type="submit" :disabled="loading">
        {{ loading ? '处理中…' : mode === 'login' ? '登 录' : '提交申请' }}
      </button>

      <p v-if="mode === 'login'" class="login-switch">
        还没有账号？
        <a href="javascript:void(0)" @click="switchMode('apply')">申请账号</a>
        <span class="login-dot">·</span>
        忘记密码？
        <a href="javascript:void(0)" @click="switchMode('apply')">重置密码</a>
      </p>
      <p v-else class="login-switch">
        已有账号？
        <a href="javascript:void(0)" @click="switchMode('login')">返回登录</a>
      </p>

      <p class="login-tip">
        {{ mode === 'login'
          ? '仅限授权用户访问，所有接口需登录后方可读写数据'
          : '已存在的账号用「同样的用户名 + 手机号」提交即为重置密码申请，均需管理员通过后生效' }}
      </p>
    </form>
  </div>
</template>
