<script setup lang="ts">
import { ref } from 'vue'
import MarkdownIt from 'markdown-it'
import { ElMessage } from 'element-plus'
import {
  createFolder,
  deleteItem,
  getTree,
  readFile,
  saveFile,
  type TreeItem,
} from '@/api/analysis'
import TreeNode from '@/components/analysis/TreeNode.vue'

const md = new MarkdownIt({ html: false, linkify: true })

const tree = ref<TreeItem[]>([])
const activePath = ref('')
const content = ref('')
const loading = ref(false)
const saving = ref(false)
const dirty = ref(false)
const collapsed = ref<Record<string, boolean>>({})
const viewMode = ref<'code' | 'preview'>('preview')

const STORAGE_KEY = 'mawork:reportlib'
interface ReportLibState {
  activePath?: string
  collapsed?: Record<string, boolean>
}
function saveState() {
  try {
    localStorage.setItem(
      STORAGE_KEY,
      JSON.stringify({
        activePath: activePath.value,
        collapsed: collapsed.value,
      }),
    )
  } catch {
    /* 忽略存储异常（隐私模式等） */
  }
}
function loadState(): ReportLibState {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    return raw ? (JSON.parse(raw) as ReportLibState) : {}
  } catch {
    return {}
  }
}
function findPathInTree(items: TreeItem[], path: string): boolean {
  for (const it of items) {
    if (it.path === path) return true
    if (it.children && findPathInTree(it.children, path)) return true
  }
  return false
}

const rendered = ref('')
function rerender() {
  rendered.value = md.render(content.value)
}

async function loadTree(restorePath?: string) {
  const res = await getTree()
  tree.value = res.tree
  if (restorePath && findPathInTree(tree.value, restorePath)) {
    await selectFile(restorePath)
  }
}

async function selectFile(path: string) {
  if (dirty.value && !confirm('当前有未保存的修改，确定切换吗？')) return
  loading.value = true
  try {
    const res = await readFile(path)
    activePath.value = path
    content.value = res.content
    dirty.value = false
    rerender()
    saveState()
  } catch (e) {
    ElMessage.error(e instanceof Error ? e.message : '加载失败')
  } finally {
    loading.value = false
  }
}

function toggleFolder(path: string) {
  collapsed.value[path] = !collapsed.value[path]
  saveState()
}

function ensureMdSuffix(name: string): string {
  return name.toLowerCase().endsWith('.md') ? name : `${name}.md`
}

async function newFile() {
  const input = prompt('输入新文件路径（支持子文件夹，如：月度复盘/2026年9月月度复盘报告）')
  if (!input || !input.trim()) return
  const path = ensureMdSuffix(input.trim().replace(/^\/+|\/+$/g, ''))
  try {
    await saveFile(path, `# ${path.split('/').pop()!.replace(/\.md$/i, '')}\n`)
    await loadTree()
    saveState()
    ElMessage.success('已创建')
    await selectFile(path)
  } catch (e) {
    ElMessage.error(e instanceof Error ? e.message : '创建失败')
  }
}

async function newFolder() {
  const input = prompt('输入新文件夹路径（如：月度复盘）')
  if (!input || !input.trim()) return
  const path = input.trim().replace(/^\/+|\/+$/g, '')
  try {
    await createFolder(path)
    await loadTree()
    saveState()
    ElMessage.success('已创建')
  } catch (e) {
    ElMessage.error(e instanceof Error ? e.message : '创建失败')
  }
}

async function onDelete(item: TreeItem) {
  const label = item.type === 'dir' ? '空文件夹' : '文件'
  if (!confirm(`确定删除${label}「${item.name}」吗？`)) return
  try {
    await deleteItem(item.path)
    if (activePath.value === item.path) {
      activePath.value = ''
      content.value = ''
      rendered.value = ''
      dirty.value = false
    }
    await loadTree()
    saveState()
    ElMessage.success('已删除')
  } catch (e) {
    ElMessage.error(e instanceof Error ? e.message : '删除失败')
  }
}

async function save() {
  if (!activePath.value) return
  saving.value = true
  try {
    await saveFile(activePath.value, content.value)
    dirty.value = false
    saveState()
    ElMessage.success('已保存')
  } catch (e) {
    ElMessage.error(e instanceof Error ? e.message : '保存失败')
  } finally {
    saving.value = false
  }
}

function onKeydown(e: KeyboardEvent) {
  if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 's') {
    e.preventDefault()
    save()
  }
}

async function loadAll() {
  const st = loadState()
  collapsed.value = st.collapsed || {}
  await loadTree(st.activePath)
  saveState()
}

defineExpose({
  async init() {
    await loadAll()
  },
  async reload() {
    await loadAll()
  },
})
</script>

<template>
  <div class="an-report" @keydown="onKeydown">
    <div class="an-report-list">
      <div class="an-report-head">
        <span class="an-report-title-tip">报告库</span>
      </div>

      <div class="an-report-actions">
        <button class="an-btn" @click="newFile">＋ 文件</button>
        <button class="an-btn" @click="newFolder">＋ 文件夹</button>
      </div>

      <div class="an-report-tree">
        <div v-if="tree.length === 0" class="an-empty">
          还没有报告。到「复盘」页生成报告后可以直接存到这里
        </div>
        <TreeNode
          v-for="item in tree"
          :key="item.path"
          :item="item"
          :active-path="activePath"
          :collapsed="collapsed"
          @select="selectFile"
          @toggle="toggleFolder"
          @delete="onDelete"
        />
      </div>
    </div>

    <div class="an-report-main">
      <div class="an-review-head">
        <div class="an-review-title">{{ activePath || '未选择文件' }}</div>
        <div class="an-review-ops">
          <span v-if="dirty" class="an-dirty">未保存</span>
          <button
            class="an-btn"
            @click="
              () => {
                viewMode = viewMode === 'code' ? 'preview' : 'code'
                if (viewMode === 'preview') rerender()
              }
            "
          >{{ viewMode === 'code' ? '预览' : '编辑' }}</button>
          <button class="an-btn primary" :disabled="saving || !activePath" @click="save">
            {{ saving ? '保存中…' : '保存' }}
          </button>
        </div>
      </div>

      <div v-if="!activePath" class="an-empty-box">从左侧选择一份报告，或新建文件</div>
      <template v-else>
        <textarea
          v-if="viewMode === 'code'"
          v-model="content"
          class="an-review-input"
          spellcheck="false"
          placeholder="Markdown 内容…"
          @input="dirty = true"
        ></textarea>
        <div v-else-if="!loading" class="md-body an-review-md" v-html="rendered"></div>
      </template>
    </div>
  </div>
</template>
