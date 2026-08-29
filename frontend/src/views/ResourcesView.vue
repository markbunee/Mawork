<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import MarkdownIt from 'markdown-it'
import { fetchTree, readMarkdown, pdfUrl, type TreeNode } from '@/api/resources'

const md = new MarkdownIt({ html: false, linkify: true })

const root = ref<TreeNode | null>(null)
const loadingTree = ref(false)
const treeError = ref('')

// 已展开的目录 path 集合
const expanded = ref<Set<string>>(new Set())

const activeFile = ref<TreeNode | null>(null)
const mdHtml = ref('')
const pdfSrc = ref('')
const loadingContent = ref(false)

interface Row {
  node: TreeNode
  depth: number
  isDir: boolean
  isOpen: boolean
}

// 根据展开状态把树扁平化为可见行
const rows = computed<Row[]>(() => {
  const out: Row[] = []
  const walk = (node: TreeNode, depth: number) => {
    const isDir = node.type === 'dir'
    const isOpen = isDir && expanded.value.has(node.path)
    out.push({ node, depth, isDir, isOpen })
    if (isDir && isOpen) {
      for (const child of node.children) walk(child, depth + 1)
    }
  }
  if (root.value) walk(root.value, 0)
  return out
})

function fileIcon(ext: string): string {
  switch (ext) {
    case '.md': case '.markdown': return '📄'
    case '.pdf': return '📕'
    case '.xlsx': case '.xls': case '.csv': return '📊'
    case '.txt': return '📃'
    default: return '📎'
  }
}

function toggleDir(path: string) {
  const s = new Set(expanded.value)
  if (s.has(path)) s.delete(path)
  else s.add(path)
  expanded.value = s
}

async function onRowClick(row: Row) {
  if (row.isDir) {
    toggleDir(row.node.path)
    return
  }
  const item = row.node
  activeFile.value = item
  mdHtml.value = ''
  pdfSrc.value = ''
  if (item.ext === '.pdf') {
    pdfSrc.value = pdfUrl(item.path)
    return
  }
  if (['.md', '.markdown', '.txt'].includes(item.ext)) {
    loadingContent.value = true
    readMarkdown(item.path)
      .then((res) => { mdHtml.value = md.render(res.content) })
      .finally(() => { loadingContent.value = false })
  }
}

async function loadTree() {
  loadingTree.value = true
  treeError.value = ''
  try {
    const tree = await fetchTree()
    root.value = tree
    // 默认展开根和第一层目录，呈现截图效果
    const s = new Set<string>([tree.path])
    for (const child of tree.children) {
      if (child.type === 'dir') s.add(child.path)
    }
    expanded.value = s
  } catch (e) {
    treeError.value = e instanceof Error ? e.message : '加载失败'
  } finally {
    loadingTree.value = false
  }
}

onMounted(loadTree)
</script>

<template>
  <div class="resources">
    <!-- 左侧目录树 -->
    <div class="res-pane">
      <div class="res-toolbar">
        <span class="res-title">资料库</span>
        <button class="res-up" @click="loadTree" title="刷新">⟳</button>
      </div>

      <div class="res-filelist">
        <div v-if="loadingTree" class="res-loading">加载中…</div>
        <div v-else-if="treeError" class="res-loading">{{ treeError }}</div>
        <div v-else-if="rows.length === 0" class="res-loading">空文件夹</div>

        <div
          v-for="row in rows"
          v-else
          :key="row.node.path || '__root__'"
          class="res-file"
          :class="{ active: !row.isDir && activeFile?.path === row.node.path }"
          :style="{ paddingLeft: `${10 + row.depth * 16}px` }"
          :title="row.node.name"
          @click="onRowClick(row)"
        >
          <span v-if="row.isDir" class="res-caret" :class="{ open: row.isOpen }">›</span>
          <span v-else class="res-caret res-caret-placeholder"></span>
          <span class="res-file-icon">{{ row.isDir ? (row.isOpen ? '📂' : '📁') : fileIcon(row.node.ext) }}</span>
          <span class="res-file-name">{{ row.depth === 0 ? 'workspaces' : row.node.name }}</span>
        </div>
      </div>
    </div>

    <!-- 右侧预览 -->
    <div class="res-preview">
      <div v-if="!activeFile" class="res-empty">选择文件进行预览</div>

      <template v-else>
        <div class="preview-head">{{ activeFile.path }}</div>
        <iframe
          v-if="activeFile.ext === '.pdf'"
          class="pdf-frame"
          :src="pdfSrc"
          title="PDF 预览"
        ></iframe>
        <div v-else-if="['.md', '.markdown', '.txt'].includes(activeFile.ext)" class="md-body">
          <div v-if="loadingContent" class="res-loading">加载中…</div>
          <div v-else v-html="mdHtml"></div>
        </div>
        <div v-else class="res-empty">
          该类型（{{ activeFile.ext || '无扩展名' }}）暂不支持在线预览
        </div>
      </template>
    </div>
  </div>
</template>
