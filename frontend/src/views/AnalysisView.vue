<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import MarkdownIt from 'markdown-it'
import { ElMessage } from 'element-plus'
import {
  listYears,
  getTree,
  readFile,
  saveFile,
  createFolder,
  deleteItem,
  type TreeItem,
} from '@/api/analysis'
import TreeNode from '@/components/analysis/TreeNode.vue'

const years = ref<string[]>([])
const year = ref(new Date().getFullYear().toString())

const tree = ref<TreeItem[]>([])
const activePath = ref('')
const content = ref('')
const loading = ref(false)
const saving = ref(false)
const dirty = ref(false)
const collapsed = ref<Record<string, boolean>>({})

const md = new MarkdownIt({ html: false, linkify: true })
const viewMode = ref<'code' | 'preview'>('code')
const rendered = computed(() => md.render(content.value))

async function loadYears() {
  const res = await listYears()
  years.value = res.years
  if (years.value.length > 0 && !years.value.includes(year.value)) {
    year.value = years.value[0]
  }
}

async function loadTree() {
  const res = await getTree(year.value)
  tree.value = res.tree
}

async function changeYear(y: string) {
  year.value = y
  activePath.value = ''
  content.value = ''
  dirty.value = false
  await loadTree()
}

async function selectFile(path: string) {
  if (dirty.value && !confirm('当前有未保存的修改，确定切换吗？')) {
    return
  }
  loading.value = true
  try {
    const res = await readFile(year.value, path)
    activePath.value = path
    content.value = res.content
    dirty.value = false
  } catch (e) {
    ElMessage.error(e instanceof Error ? e.message : '加载失败')
  } finally {
    loading.value = false
  }
}

function toggleFolder(path: string) {
  collapsed.value[path] = !collapsed.value[path]
}

function ensureMdSuffix(name: string): string {
  return name.toLowerCase().endsWith('.md') ? name : `${name}.md`
}

async function newFile() {
  const input = prompt('输入新文件路径（支持子文件夹，如：月度复盘/2026年9月月度复盘报告）')
  if (!input || !input.trim()) return
  const path = ensureMdSuffix(input.trim().replace(/^\/+|\/+$/g, ''))
  try {
    await saveFile(year.value, path, `# ${path.split('/').pop()!.replace(/\.md$/i, '')}\n`)
    await loadTree()
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
    await createFolder(year.value, path)
    await loadTree()
    ElMessage.success('已创建')
  } catch (e) {
    ElMessage.error(e instanceof Error ? e.message : '创建失败')
  }
}

async function onDelete(item: TreeItem) {
  const label = item.type === 'dir' ? '空文件夹' : '文件'
  if (!confirm(`确定删除${label}「${item.name}」吗？`)) return
  try {
    await deleteItem(year.value, item.path)
    if (activePath.value === item.path) {
      activePath.value = ''
      content.value = ''
      dirty.value = false
    }
    await loadTree()
    ElMessage.success('已删除')
  } catch (e) {
    ElMessage.error(e instanceof Error ? e.message : '删除失败')
  }
}

async function save() {
  if (!activePath.value) return
  saving.value = true
  try {
    await saveFile(year.value, activePath.value, content.value)
    dirty.value = false
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

onMounted(async () => {
  await loadYears()
  await loadTree()
})
</script>

<template>
  <div class="daily" @keydown="onKeydown">
    <div class="daily-list analysis-list">
      <div class="list-header">
        <select v-model="year" class="year-select" @change="changeYear(year)">
          <option v-for="y in years" :key="y" :value="y">{{ y }}年</option>
        </select>
      </div>

      <div class="analysis-actions">
        <button class="btn-new" @click="newFile">＋ 文件</button>
        <button class="btn-new" @click="newFolder">＋ 文件夹</button>
      </div>

      <div class="daily-tree">
        <div v-if="tree.length === 0" class="empty-tip">
          还没有报告，点「＋ 文件」新建；复盘/计划报告会自动写入这里
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

    <div class="daily-editor">
      <div class="editor-head">
        <div class="editor-title">
          <span class="date-label">{{ activePath || '未选择文件' }}</span>
        </div>
        <div class="editor-actions">
          <span v-if="dirty" class="dirty-hint">未保存</span>
          <button
            class="switch-btn"
            :class="{ active: viewMode === 'preview' }"
            @click="viewMode = viewMode === 'code' ? 'preview' : 'code'"
          >{{ viewMode === 'code' ? '预览' : '代码' }}</button>
          <button class="btn-save" :disabled="saving || !activePath" @click="save">
            {{ saving ? '保存中…' : '保存' }}
          </button>
        </div>
      </div>

      <div v-if="!activePath" class="res-empty">
        从左侧选择一份报告，或新建文件
      </div>
      <template v-else>
        <textarea
          v-if="viewMode === 'code'"
          v-model="content"
          class="editor-textarea"
          spellcheck="false"
          placeholder="Markdown 内容…"
          @input="dirty = true"
        ></textarea>
        <div v-else class="md-body" v-html="rendered"></div>
      </template>
    </div>
  </div>
</template>

<style scoped>
.analysis-list {
  width: 260px;
}

.analysis-actions {
  display: flex;
  gap: 8px;
  margin-bottom: 12px;
}

.tree-children {
  padding-left: 14px;
}

.tree-file {
  display: flex;
  align-items: center;
}

.tree-file .date-text {
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.tree-node :deep(.del-btn) {
  opacity: 0;
}

.tree-node:hover > .month-head .del-btn,
.tree-node:hover > .tree-file .del-btn {
  opacity: 1;
}
</style>
