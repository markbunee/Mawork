<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  approveApplication,
  createUser,
  deleteUser,
  listApplications,
  listUsers,
  rejectApplication,
  resetPassword,
  setUserRole,
  setUserStatus,
  kindLabel,
  statusLabel,
  type ApplicationItem,
  type UserItem,
} from '@/api/user'
import { getUid } from '@/utils/auth'

const users = ref<UserItem[]>([])
const apps = ref<ApplicationItem[]>([])
const loading = ref(false)
const appFilter = ref<'pending' | 'all'>('pending')

// 新建成员（免审批直接建号）
const newOpen = ref(false)
const form = ref({ username: '', phone: '', password: '', role: 'member' as 'admin' | 'member' })

// 重置密码结果：临时密码只在这里显示一次
const tempPwd = ref<{ username: string; password: string } | null>(null)

const me = getUid()
const pendingCount = computed(() => apps.value.filter((a) => a.status === 'pending').length)

async function load() {
  loading.value = true
  try {
    const [u, a] = await Promise.all([listUsers(), listApplications(appFilter.value)])
    users.value = u.items
    apps.value = a.items
  } catch (e) {
    ElMessage.error(e instanceof Error ? e.message : '加载失败')
  } finally {
    loading.value = false
  }
}

async function onApprove(a: ApplicationItem) {
  try {
    const tip = a.kind === 'reset' ? '通过后该成员的原密码立即失效，改用本次提交的密码' : '通过后该成员即可登录'
    await ElMessageBox.confirm(`通过「${a.username}」的${kindLabel[a.kind]}申请？${tip}。`, '审批', {
      type: 'warning',
    })
  } catch {
    return
  }
  try {
    await approveApplication(a.id)
    ElMessage.success('已通过')
    await load()
  } catch (e) {
    ElMessage.error(e instanceof Error ? e.message : '操作失败')
  }
}

async function onReject(a: ApplicationItem) {
  try {
    const { value } = await ElMessageBox.prompt('驳回理由（选填）', '驳回申请', {
      inputPlaceholder: '例如：信息不符',
      inputValue: '',
    })
    await rejectApplication(a.id, String(value || ''))
    ElMessage.success('已驳回')
    await load()
  } catch (e) {
    if (e instanceof Error && e.message) ElMessage.error(e.message)
  }
}

async function onReset(u: UserItem) {
  try {
    await ElMessageBox.confirm(`重置「${u.username}」的密码？旧密码将立即失效。`, '重置密码', {
      type: 'warning',
    })
  } catch {
    return
  }
  try {
    const res = await resetPassword(u.id)
    tempPwd.value = { username: res.user.username, password: res.temp_password }
  } catch (e) {
    ElMessage.error(e instanceof Error ? e.message : '重置失败')
  }
}

async function onToggleStatus(u: UserItem) {
  try {
    await setUserStatus(u.id, u.status === 'active' ? 'disabled' : 'active')
    ElMessage.success(u.status === 'active' ? '已停用' : '已启用')
    await load()
  } catch (e) {
    ElMessage.error(e instanceof Error ? e.message : '操作失败')
  }
}

async function onToggleRole(u: UserItem) {
  const next = u.role === 'admin' ? 'member' : 'admin'
  try {
    await setUserRole(u.id, next)
    ElMessage.success(next === 'admin' ? '已设为管理员' : '已降为普通成员')
    await load()
  } catch (e) {
    ElMessage.error(e instanceof Error ? e.message : '操作失败')
  }
}

async function onDelete(u: UserItem) {
  try {
    await ElMessageBox.confirm(
      `删除「${u.username}」？该成员的**全部业务数据**（日报、记账、日程等）将一并清除，且不可恢复。`,
      '删除成员',
      { type: 'warning', dangerouslyUseHTMLString: false },
    )
  } catch {
    return
  }
  try {
    await deleteUser(u.id)
    ElMessage.success('已删除')
    await load()
  } catch (e) {
    ElMessage.error(e instanceof Error ? e.message : '删除失败')
  }
}

async function onCreate() {
  if (!form.value.username.trim() || !form.value.password) {
    ElMessage.warning('请填写用户名与密码')
    return
  }
  try {
    await createUser({
      username: form.value.username.trim(),
      phone: form.value.phone.trim(),
      password: form.value.password,
      role: form.value.role,
    })
    ElMessage.success('已创建，该成员可直接登录')
    form.value = { username: '', phone: '', password: '', role: 'member' }
    newOpen.value = false
    await load()
  } catch (e) {
    ElMessage.error(e instanceof Error ? e.message : '创建失败')
  }
}

function copyTemp() {
  if (!tempPwd.value) return
  navigator.clipboard?.writeText(tempPwd.value.password).then(
    () => ElMessage.success('已复制'),
    () => ElMessage.warning('复制失败，请手动记录'),
  )
}

onMounted(load)
</script>

<template>
  <div class="users">
    <div class="users-head">
      <div>
        <h2 class="users-title">用户管理</h2>
        <p class="users-sub">
          共 {{ users.length }} 位成员<span v-if="pendingCount"> · {{ pendingCount }} 条待审批</span>
        </p>
      </div>
      <div class="users-actions">
        <button class="u-btn" :disabled="loading" @click="load">刷新</button>
        <button class="u-btn primary" @click="newOpen = !newOpen">
          {{ newOpen ? '收起' : '直接建号' }}
        </button>
      </div>
    </div>

    <!-- 直接建号（免审批） -->
    <div v-if="newOpen" class="u-card">
      <h3 class="u-card-title">直接建号</h3>
      <div class="u-form">
        <label class="u-field">
          <span>用户名</span>
          <input v-model="form.username" type="text" placeholder="字母/数字/下划线，3-32 位" />
        </label>
        <label class="u-field">
          <span>手机号</span>
          <input v-model="form.phone" type="tel" inputmode="numeric" placeholder="选填，用于自助改密" />
        </label>
        <label class="u-field">
          <span>密码</span>
          <input v-model="form.password" type="text" placeholder="至少 8 位" />
        </label>
        <label class="u-field">
          <span>角色</span>
          <select v-model="form.role">
            <option value="member">普通成员</option>
            <option value="admin">管理员</option>
          </select>
        </label>
        <button class="u-btn primary" @click="onCreate">创建</button>
      </div>
    </div>

    <!-- 申请审批 -->
    <div class="u-card">
      <div class="u-card-head">
        <h3 class="u-card-title">成员申请</h3>
        <div class="u-seg">
          <button :class="{ on: appFilter === 'pending' }" @click="appFilter = 'pending'; load()">
            待审批
          </button>
          <button :class="{ on: appFilter === 'all' }" @click="appFilter = 'all'; load()">
            全部
          </button>
        </div>
      </div>

      <p v-if="apps.length === 0" class="u-empty">暂无申请</p>
      <ul v-else class="u-list">
        <li v-for="a in apps" :key="a.id" class="u-row">
          <div class="u-main">
            <span class="u-name">{{ a.username }}</span>
            <span class="u-tag" :class="a.kind">{{ kindLabel[a.kind] }}</span>
            <span class="u-tag ghost">{{ statusLabel[a.status] }}</span>
          </div>
          <div class="u-meta">
            <span>手机号 {{ a.phone || '—' }}</span>
            <span>提交于 {{ a.created_at }}</span>
            <span v-if="a.note">备注：{{ a.note }}</span>
          </div>
          <div v-if="a.status === 'pending'" class="u-row-actions">
            <button class="u-btn primary" @click="onApprove(a)">通过</button>
            <button class="u-btn" @click="onReject(a)">驳回</button>
          </div>
        </li>
      </ul>
    </div>

    <!-- 成员列表 -->
    <div class="u-card">
      <h3 class="u-card-title">成员列表</h3>
      <p v-if="users.length === 0" class="u-empty">暂无成员</p>
      <ul v-else class="u-list">
        <li v-for="u in users" :key="u.id" class="u-row">
          <div class="u-main">
            <span class="u-name">{{ u.username }}</span>
            <span class="u-tag" :class="u.role === 'admin' ? 'reset' : 'new'">
              {{ u.role === 'admin' ? '管理员' : '成员' }}
            </span>
            <span v-if="u.status !== 'active'" class="u-tag ghost">已停用</span>
            <span v-if="u.id === me" class="u-tag ghost">当前登录</span>
          </div>
          <div class="u-meta">
            <span>手机号 {{ u.phone || '—' }}</span>
            <span>创建 {{ u.created_at }}</span>
            <span>最近登录 {{ u.last_login || '从未' }}</span>
          </div>
          <div class="u-row-actions">
            <button class="u-btn" @click="onReset(u)">重置密码</button>
            <button class="u-btn" @click="onToggleStatus(u)">
              {{ u.status === 'active' ? '停用' : '启用' }}
            </button>
            <button class="u-btn" @click="onToggleRole(u)">
              {{ u.role === 'admin' ? '降为成员' : '设为管理员' }}
            </button>
            <button class="u-btn danger" :disabled="u.id === me" @click="onDelete(u)">删除</button>
          </div>
        </li>
      </ul>
    </div>

    <!-- 临时密码（仅显示一次） -->
    <div v-if="tempPwd" class="u-mask" @click.self="tempPwd = null">
      <div class="u-dialog">
        <h3 class="u-card-title">临时密码已生成</h3>
        <p class="u-meta">成员：{{ tempPwd.username }}</p>
        <div class="u-pwd">{{ tempPwd.password }}</div>
        <p class="u-warn">请立即复制并告知该成员。此密码只显示这一次，关闭后无法再查看。</p>
        <div class="u-row-actions">
          <button class="u-btn primary" @click="copyTemp">复制</button>
          <button class="u-btn" @click="tempPwd = null">我已记录</button>
        </div>
      </div>
    </div>
  </div>
</template>
