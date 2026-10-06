<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import MarkdownIt from 'markdown-it'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  createFolder,
  deleteItem,
  fetchTree,
  fetchPdfUrl,
  precheckUpload,
  readMarkdown,
  renameItem,
  saveTextFile,
  uploadFiles,
  userZipUrl,
  type TreeNode,
} from '@/api/resources'
import { download } from '@/api/http'
import { getUid } from '@/utils/auth'
import { useIsMobile } from '@/utils/useIsMobile'

const route = useRoute()
const isMobile = useIsMobile()
const actionOpen = ref(false)
const md = new MarkdownIt({ html: false, linkify: true })
const MD_EXTS = ['.md', '.markdown', '.txt']

const root = ref<TreeNode | null>(null)
const loadingTree = ref(false)
const treeError = ref('')
const expanded = ref<Set<string>>(new Set())

const activeFile = ref<TreeNode | null>(null)
const mdHtml = ref('')
const pdfSrc = ref('')
const loadingContent = ref(false)

// ---------------------------------------------------------------------------
// Markdown 在线编辑
// ---------------------------------------------------------------------------
const editing = ref(false)
const draft = ref('')
const saved = ref('')
/** 编辑中的文件路径：保存以它为准，避免切换文件后误写到别处 */
const editingPath = ref('')
const saving = ref(false)
const taRef = ref<HTMLTextAreaElement | null>(null)

const isMd = computed(() => MD_EXTS.includes(activeFile.value?.ext || ''))
const dirty = computed(() => editing.value && draft.value !== saved.value)

/** 在光标处插入语法；selected 为选中文本（用于包裹） */
function wrap(before: string, after = before, placeholder = '') {
  const ta = taRef.value
  if (!ta) return
  const s = ta.selectionStart
  const e = ta.selectionEnd
  const sel = draft.value.slice(s, e) || placeholder
  draft.value = draft.value.slice(0, s) + before + sel + after + draft.value.slice(e)
  void Promise.resolve().then(() => {
    ta.focus()
    ta.setSelectionRange(s + before.length, s + before.length + sel.length)
  })
}

const TOOLS = [
  { tip: '加粗', run: () => wrap('**', '**', '粗体') },
  { tip: '斜体', run: () => wrap('*', '*', '斜体') },
  { tip: '删除线', run: () => wrap('~~', '~~', '删除') },
  { tip: '标题', run: () => wrap('## ', '', '标题') },
  { tip: '引用', run: () => wrap('> ', '', '引用') },
  { tip: '无序列表', run: () => wrap('- ', '', '列表项') },
  { tip: '有序列表', run: () => wrap('1. ', '', '列表项') },
  { tip: '任务项', run: () => wrap('- [ ] ', '', '待办') },
  { tip: '行内代码', run: () => wrap('`', '`', 'code') },
  { tip: '代码块', run: () => wrap('```\n', '\n```', 'code') },
  { tip: '链接', run: () => wrap('[', '](https://)', '链接文字') },
  { tip: '表格', run: () => wrap('| 列1 | 列2 |\n| --- | --- |\n| ', ' |  |', '内容') },
]

function enterEdit() {
  if (!activeFile.value) return
  editingPath.value = activeFile.value.path
  draft.value = saved.value
  editing.value = true
}

function exitEdit() {
  editing.value = false
  draft.value = ''
  editingPath.value = ''
}

async function saveMd() {
  if (!editingPath.value || saving.value) return
  saving.value = true
  try {
    await saveTextFile(editingPath.value, draft.value)
    saved.value = draft.value
    mdHtml.value = md.render(draft.value)
    ElMessage.success('已保存')
    await loadTree()
  } catch (e) {
    ElMessage.error(e instanceof Error ? e.message : '保存失败')
  } finally {
    saving.value = false
  }
}

// ---------------------------------------------------------------------------
// PDF 预览：URL 缓存 + 票据续期
// ---------------------------------------------------------------------------
// 早期实现是「fetch 带令牌 → 整份下成 blob → createObjectURL」，
// 代价是：① 必须等整份下载完才渲染；② blob: 下浏览器 PDF 阅读器无法发
// HTTP Range 请求，只能整份拉取、无法按需分页；③ 每次切回该文件都重新
// 全量下载，且内存里常驻一份完整副本。
// 现改为向后端换一张短时票据，把「真实 URL + 票据」直接交给 iframe，
// 于是 Range / ETag / 浏览器缓存全部生效。
const pdfUrlCache = new Map<string, { url: string; expiresAt: number }>()
const RENEW_AHEAD_MS = 60_000
const RENEW_INTERVAL_MS = 30_000
let renewTimer: ReturnType<typeof setInterval> | null = null

function stopRenew() {
  if (renewTimer !== null) {
    clearInterval(renewTimer)
    renewTimer = null
  }
}

async function openPdf(path: string) {
  const cached = pdfUrlCache.get(path)
  if (cached && cached.expiresAt - Date.now() > RENEW_AHEAD_MS) {
    pdfSrc.value = cached.url
    startRenew()
    return
  }
  loadingContent.value = true
  try {
    const res = await fetchPdfUrl(path)
    pdfUrlCache.set(path, { url: res.url, expiresAt: Date.now() + res.expires_in * 1000 })
    pdfSrc.value = res.url
  } catch {
    pdfSrc.value = ''
  } finally {
    loadingContent.value = false
  }
  startRenew()
}

function startRenew() {
  stopRenew()
  renewTimer = setInterval(() => {
    const path = activeFile.value?.ext === '.pdf' ? activeFile.value.path : null
    if (!path) {
      stopRenew()
      return
    }
    const cached = pdfUrlCache.get(path)
    if (cached && cached.expiresAt - Date.now() > RENEW_AHEAD_MS) return
    void fetchPdfUrl(path).then((res) => {
      pdfUrlCache.set(path, {
        url: res.url,
        expiresAt: Date.now() + res.expires_in * 1000,
      })
      if (activeFile.value?.path === path) pdfSrc.value = res.url
    })
  }, RENEW_INTERVAL_MS)
}

interface Row {
  node: TreeNode
  depth: number
  isDir: boolean
  isOpen: boolean
}

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

async function openNode(node: TreeNode) {
  // 切换文件前若改了内容未保存，先问一句，避免白丢
  if (editing.value && dirty.value && editingPath.value !== node.path) {
    try {
      await ElMessageBox.confirm('当前文件有未保存的修改，确定放弃吗？', '未保存', {
        type: 'warning',
        confirmButtonText: '放弃修改',
        cancelButtonText: '继续编辑',
      })
    } catch {
      return
    }
    exitEdit()
  }
  activeFile.value = node
  mdHtml.value = ''
  pdfSrc.value = ''
  if (node.ext === '.pdf') {
    void openPdf(node.path)
    return
  }
  stopRenew()
  if (MD_EXTS.includes(node.ext)) {
    loadingContent.value = true
    try {
      const res = await readMarkdown(node.path)
      saved.value = res.content
      mdHtml.value = md.render(res.content)
    } catch (e) {
      ElMessage.error(e instanceof Error ? e.message : '读取失败')
    } finally {
      loadingContent.value = false
    }
  }
}

async function onRowClick(row: Row) {
  if (row.isDir) {
    toggleDir(row.node.path)
    return
  }
  await openNode(row.node)
}

// ---------------------------------------------------------------------------
// 文件操作
// ---------------------------------------------------------------------------
const busy = ref('')
const dragOver = ref(false)
const fileInput = ref<HTMLInputElement | null>(null)

/** 目标目录：选中的是目录就用它，选中文件就用其所在目录，未选中则根目录 */
const targetDir = computed(() => {
  const a = activeFile.value
  if (!a) return ''
  if (a.type === 'dir') return a.path
  const parts = a.path.split('/')
  parts.pop()
  return parts.join('/')
})

const targetDirLabel = computed(() => targetDir.value || '根目录')

function humanSize(n: number): string {
  if (n < 1024) return `${n} B`
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`
  return `${(n / 1024 / 1024).toFixed(1)} MB`
}

function joinPath(dir: string, name: string): string {
  return dir ? `${dir}/${name}` : name
}

/** 下载当前选中文件 */
async function onDownload() {
  const f = activeFile.value
  if (!f || f.type === 'dir') return
  // 先确认，避免一点就下载
  try {
    await ElMessageBox.confirm(`确认下载「${f.name}」吗？`, '下载文件', {
      type: 'info',
      confirmButtonText: '下载',
      cancelButtonText: '取消',
    })
  } catch {
    return
  }
  busy.value = 'download'
  try {
    await download(
      `/api/resources/download?path=${encodeURIComponent(f.path)}`,
      f.name,
    )
    ElMessage.success('已开始下载')
  } catch (e) {
    ElMessage.error(e instanceof Error ? e.message : '下载失败')
  } finally {
    busy.value = ''
  }
}

/** 下载当前用户全部文件为 zip 压缩包 */
async function onDownloadAll() {
  const uid = getUid()
  const fname = uid ? `u${uid}-files.zip` : 'workspaces-files.zip'
  // 先确认，避免一点就下载
  try {
    await ElMessageBox.confirm(
      `确认把当前账号（${
        uid ? `u${uid}` : '全部'
      }）的整个资料目录打包成 zip 下载吗？\n包含资料文件与数据库（.db）等全部内容，下载后可在本地解压还原。`,
      '下载全部文件',
      {
        type: 'info',
        confirmButtonText: '下载',
        cancelButtonText: '取消',
      },
    )
  } catch {
    return
  }
  busy.value = 'zip'
  try {
    await download(userZipUrl(), fname)
    ElMessage.success('已开始下载压缩包')
  } catch (e) {
    ElMessage.error(e instanceof Error ? e.message : '下载失败')
  } finally {
    busy.value = ''
  }
}

/** 新建空白文件（md / markdown / txt） */
async function onNewFile() {
  try {
    const { value } = await ElMessageBox.prompt(
      '新文件名称（请带扩展名，如 笔记.md / 清单.txt）',
      '新建文件',
      {
        confirmButtonText: '创建',
        cancelButtonText: '取消',
        inputValue: 'untitled.md',
        inputValidator: (v: string) => {
          const s = (v || '').trim()
          if (!s) return '名称不能为空'
          if (s.includes('/') || s.includes('\\')) return '名称不能包含斜杠'
          if (s === '.' || s === '..') return '名称不合法'
          if (!s.includes('.')) return '请带上扩展名（如 .md / .txt）'
          const ext = s.slice(s.lastIndexOf('.') + 1).toLowerCase()
          if (!['md', 'markdown', 'txt'].includes(ext)) {
            return '仅支持 .md / .markdown / .txt'
          }
          return true
        },
      },
    )
    const name = value.trim()
    const path = joinPath(targetDir.value, name)
    await saveTextFile(path, '')
    ElMessage.success('已创建文件')
    await loadTree()
    const found = findNode(path)
    if (found) await openNode(found)
  } catch {
    /* 用户取消 */
  }
}

/**
 * 上传前的重名确认：列出全部冲突，一次询问。
 * 静默覆盖是数据丢失最常见的来源，必须让用户先看见。
 */
async function confirmOverwrite(
  conflicts: { name: string; size: number; is_dir: boolean; mtime: number }[],
  dir: string,
): Promise<'all' | 'skip' | 'cancel'> {
  const lines = conflicts.slice(0, 12).map((c) => {
    const kind = c.is_dir ? '目录' : humanSize(c.size)
    const when = c.mtime ? new Date(c.mtime * 1000).toLocaleString('zh-CN') : ''
    return `· ${c.name}（${kind}，${when}）`
  })
  const more = conflicts.length > 12 ? `\n… 另有 ${conflicts.length - 12} 个` : ''
  try {
    await ElMessageBox.confirm(
      `以下 ${conflicts.length} 个文件在「${dir || '根目录'}」已存在：\n\n`
      + `${lines.join('\n')}${more}\n\n`
      + '「覆盖」会用新文件替换它们；「跳过」只上传其余文件。',
      '存在同名文件',
      {
        type: 'warning',
        distinguishCancelAndClose: true,
        confirmButtonText: '覆盖',
        cancelButtonText: '跳过同名',
      },
    )
    return 'all'
  } catch (e) {
    // distinguishCancelAndClose：cancel=跳过同名，close=取消整个上传
    return (e as unknown as { action?: string })?.action === 'cancel' ? 'skip' : 'cancel'
  }
}

async function doUpload(list: FileList | File[] | null) {
  const files = list ? Array.from(list) : []
  if (!files.length) return
  const dir = targetDir.value

  // 先让用户确认：列明要上传哪些文件、传到哪里，避免一点就上传
  const head = files.slice(0, 12).map((f) => `· ${f.name}`).join('\n')
  const more = files.length > 12 ? `\n… 另有 ${files.length - 12} 个` : ''
  try {
    await ElMessageBox.confirm(
      `确认上传以下 ${files.length} 个文件到「${dir || '根目录'}」吗？\n\n${head}${more}`,
      '确认上传',
      {
        type: 'info',
        confirmButtonText: '上传',
        cancelButtonText: '取消',
      },
    )
  } catch {
    return
  }

  busy.value = 'precheck'
  try {
    const check = await precheckUpload(dir, files.map((f) => f.name))
    let toSend: File[]
    if (!check.has_conflict) {
      toSend = files
    } else {
      const choice = await confirmOverwrite(check.conflicts, dir)
      if (choice === 'cancel') return
      if (choice === 'skip') {
        const dup = new Set(check.conflicts.map((c) => c.name))
        toSend = files.filter((f) => !dup.has(f.name))
        if (!toSend.length) {
          ElMessage.info('没有需要上传的新文件')
          return
        }
      } else {
        toSend = files
      }
    }
    busy.value = 'upload'
    const res = await uploadFiles(dir, toSend)
    const parts = [`已上传 ${res.uploaded} 个文件`]
    if (res.overwritten > 0) parts.push(`覆盖 ${res.overwritten} 个`)
    parts.push(res.total_size)
    ElMessage.success(parts.join(' · '))
    await loadTree()
  } catch (e) {
    ElMessage.error(e instanceof Error ? e.message : '上传失败')
  } finally {
    busy.value = ''
  }
}

function pickFiles() {
  fileInput.value?.click()
}

async function onFilePicked(e: Event) {
  const input = e.target as HTMLInputElement
  await doUpload(input.files)
  input.value = '' // 允许重复选择同一文件
}

/** 关闭预览（仅手机端上滑覆盖层使用） */
function closePreview() {
  if (editing.value && dirty.value) {
    ElMessageBox.confirm('当前文件有未保存的修改，确定放弃吗？', '未保存', {
      type: 'warning',
      confirmButtonText: '放弃修改',
      cancelButtonText: '继续编辑',
    }).then(() => {
      exitEdit()
      activeFile.value = null
      mdHtml.value = ''
      pdfSrc.value = ''
      stopRenew()
    }).catch(() => {})
    return
  }
  activeFile.value = null
  mdHtml.value = ''
  pdfSrc.value = ''
  stopRenew()
}

/** 手机端悬浮「+」操作表：把各功能分流到既有处理函数 */
function fabAction(kind: 'upload' | 'newfile' | 'newfolder' | 'zip' | 'refresh') {
  actionOpen.value = false
  if (kind === 'upload') pickFiles()
  else if (kind === 'newfile') void onNewFile()
  else if (kind === 'newfolder') void onNewFolder()
  else if (kind === 'zip') void onDownloadAll()
  else void loadTree()
}

// 拖拽：必须 preventDefault，否则浏览器直接打开文件、页面跳走
function onDragOver(e: DragEvent) {
  e.preventDefault()
  e.stopPropagation()
  dragOver.value = true
}

function onDragLeave(e: DragEvent) {
  e.preventDefault()
  e.stopPropagation()
  if (e.currentTarget === e.target) dragOver.value = false
}

async function onDrop(e: DragEvent) {
  e.preventDefault()
  e.stopPropagation()
  dragOver.value = false
  if (e.dataTransfer?.files?.length) await doUpload(e.dataTransfer.files)
}

async function onNewFolder() {
  try {
    const { value } = await ElMessageBox.prompt('新文件夹名称', '新建文件夹', {
      confirmButtonText: '创建',
      cancelButtonText: '取消',
      inputValidator: (v: string) => {
        const s = (v || '').trim()
        if (!s) return '名称不能为空'
        if (s.includes('/') || s.includes('\\')) return '名称不能包含斜杠'
        if (s === '.' || s === '..') return '名称不合法'
        return true
      },
    })
    await createFolder(joinPath(targetDir.value, value.trim()))
    ElMessage.success('已创建')
    await loadTree()
  } catch {
    /* 用户取消 */
  }
}

async function onRename() {
  const f = activeFile.value
  if (!f) return
  try {
    const { value } = await ElMessageBox.prompt('新名称', '重命名', {
      confirmButtonText: '重命名',
      cancelButtonText: '取消',
      inputValue: f.name,
      inputValidator: (v: string) => {
        const s = (v || '').trim()
        if (!s) return '名称不能为空'
        if (s.includes('/') || s.includes('\\')) return '名称不能包含斜杠'
        return true
      },
    })
    const name = value.trim()
    if (name === f.name) return
    const parts = f.path.split('/')
    parts.pop()
    const newPath = joinPath(parts.join('/'), name)
    await renameItem(f.path, newPath)
    ElMessage.success('已重命名')
    await loadTree()
    const found = findNode(newPath)
    if (found) await openNode(found)
  } catch {
    /* 用户取消 */
  }
}

async function onDelete() {
  const f = activeFile.value
  if (!f) return
  try {
    await ElMessageBox.confirm(
      `确定删除「${f.name}」吗？${f.type === 'dir' ? '\n目录必须为空才能删除。' : ''}`
      + '\n注意：删除后无法撤销。',
      '确认删除',
      {
        type: 'warning',
        confirmButtonText: '删除',
        cancelButtonText: '取消',
        confirmButtonClass: 'danger',
      },
    )
    await deleteItem(f.path)
    ElMessage.success('已删除')
    activeFile.value = null
    mdHtml.value = ''
    pdfSrc.value = ''
    stopRenew()
    await loadTree()
  } catch {
    /* 用户取消 */
  }
}

function findNode(path: string): TreeNode | null {
  if (!root.value) return null
  const find = (n: TreeNode): TreeNode | null => {
    if (n.path === path) return n
    for (const c of n.children) {
      const r = find(c)
      if (r) return r
    }
    return null
  }
  return find(root.value)
}

async function loadTree() {
  loadingTree.value = true
  treeError.value = ''
  try {
    root.value = await fetchTree()
    expanded.value = new Set()
    applyInitialPath()
  } catch (e) {
    treeError.value = e instanceof Error ? e.message : '加载失败'
  } finally {
    loadingTree.value = false
  }
}

function applyInitialPath() {
  const target = route.query.path
  if (typeof target !== 'string' || !target || !root.value) return
  const node = findNode(target)
  if (!node) return
  const parts = target.split('/')
  const s = new Set(expanded.value)
  let acc = ''
  for (const part of parts.slice(0, -1)) {
    acc = acc ? `${acc}/${part}` : part
    s.add(acc)
  }
  expanded.value = s
  void openNode(node)
}

onMounted(loadTree)
onBeforeUnmount(stopRenew)
</script>
<template>
  <div
    class="resources"
    :class="{ 'drop-active': dragOver }"
    @dragover="onDragOver"
    @dragleave="onDragLeave"
    @drop="onDrop"
  >
    <div class="res-pane">
      <div class="res-toolbar">
        <span class="res-title">资料库</span>
        <div class="res-tools">
          <div class="res-tools-group">
            <button class="btn-solid" title="上传文件" :disabled="!!busy" @click="pickFiles">⬆ 上传文件</button>
            <button title="新建文件" :disabled="!!busy" @click="onNewFile">📄 新建文件</button>
            <button title="新建文件夹" :disabled="!!busy" @click="onNewFolder">📁 新建文件夹</button>
          </div>
          <div class="res-tools-group res-tools-end">
            <button class="btn-solid" title="下载全部文件(zip)" :disabled="!!busy" @click="onDownloadAll">{{ busy === 'zip' ? '打包中…' : '⬇ 下载全部' }}</button>
            <button class="btn-icon" title="刷新" :disabled="!!busy" @click="loadTree">⟳</button>
          </div>
        </div>
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
          :class="{ active: activeFile?.path === row.node.path, 'is-dir': row.isDir }"
          :style="{ paddingLeft: (10 + row.depth * 16) + 'px' }"
          :title="row.node.name"
          @click="onRowClick(row)"
        >
          <span v-if="row.isDir" class="res-caret" :class="{ open: row.isOpen }">›</span>
          <span v-else class="res-caret res-caret-placeholder"></span>
          <span class="res-file-icon">{{ row.isDir ? (row.isOpen ? '📂' : '📁') : fileIcon(row.node.ext) }}</span>
          <span class="res-file-name">{{ row.depth === 0 ? 'workspaces' : row.node.name }}</span>
        </div>
      </div>

      <p class="res-tip">把文件拖到此处即可上传到「{{ targetDirLabel }}」</p>
      <input ref="fileInput" type="file" multiple class="res-file-input" @change="onFilePicked" />
    </div>

    <div class="res-preview">
      <div v-if="!activeFile" class="res-empty">选择文件进行预览</div>

      <template v-else>
        <div class="preview-head">
          <button v-if="isMobile" class="res-close" aria-label="返回" @click="closePreview">‹ 返回</button>
          <span class="preview-path" :title="activeFile.path">{{ activeFile.path }}</span>
          <div class="preview-actions">
            <button
              v-if="activeFile.type === 'file'"
              :disabled="!!busy"
              title="下载这个文件"
              @click="onDownload"
            >{{ busy === 'download' ? '下载中…' : '⬇ 下载' }}</button>
            <button v-if="isMd && !editing" title="在线编辑" @click="enterEdit">✎ 编辑</button>
            <button
              v-if="editing"
              class="primary"
              :disabled="saving || !dirty"
              @click="saveMd"
            >{{ saving ? '保存中…' : (dirty ? '保存' : '已保存') }}</button>
            <button v-if="editing" @click="exitEdit">取消</button>
            <button title="重命名" @click="onRename">重命名</button>
            <button class="danger" title="删除" @click="onDelete">删除</button>
          </div>
        </div>

        <template v-if="activeFile.ext === '.pdf'">
          <div v-if="!pdfSrc" class="res-loading">加载中…</div>
          <iframe v-else class="pdf-frame" :src="pdfSrc" title="PDF 预览"></iframe>
        </template>

        <div v-else-if="isMd && editing" class="md-editor">
          <div class="md-tools">
            <button
              v-for="t in TOOLS"
              :key="t.tip"
              :title="t.tip"
              @click="t.run()"
            >{{ t.tip }}</button>
            <span class="md-tools-hint">编辑的是 {{ editingPath }}</span>
          </div>
          <textarea
            ref="taRef"
            v-model="draft"
            class="md-ta"
            spellcheck="false"
            placeholder="用 Markdown 写点什么…"
          ></textarea>
        </div>
        <div v-else-if="isMd" class="md-body">
          <div v-if="loadingContent" class="res-loading">加载中…</div>
          <div v-else v-html="mdHtml"></div>
        </div>
        <div v-else class="res-empty">
          该类型（{{ activeFile.ext || '无扩展名' }}）不支持在线预览，可下载后查看
        </div>
      </template>
    </div>

    <div v-if="dragOver" class="res-drop-mask">
      <div class="res-drop-box">
        <strong>松开以上传</strong>
        <span>目标目录：{{ targetDirLabel }}</span>
        <span v-if="busy" class="res-drop-busy">{{ busy === 'precheck' ? '检查重名…' : '上传中…' }}</span>
      </div>
    </div>

    <!-- 手机端悬浮操作按钮（桌面隐藏）：把上传/新建/下载全部收进操作表 -->
    <button v-if="isMobile" class="res-fab" aria-label="资料操作" @click="actionOpen = true">＋</button>

    <!-- 手机端操作底部弹层 -->
    <div v-if="isMobile && actionOpen" class="m-mask" @click="actionOpen = false">
      <div class="m-sheet" @click.stop>
        <div class="m-sheet-grab"></div>
        <h2 class="m-sheet-title">资料操作</h2>
        <button class="m-sheet-btn" @click="fabAction('upload')">⬆ 上传文件</button>
        <button class="m-sheet-btn" @click="fabAction('newfile')">📄＋ 新建文件</button>
        <button class="m-sheet-btn" @click="fabAction('newfolder')">📁＋ 新建文件夹</button>
        <button class="m-sheet-btn" @click="fabAction('zip')">⬇ 下载全部（zip）</button>
        <button class="m-sheet-btn" @click="fabAction('refresh')">⟳ 刷新</button>
        <button class="m-sheet-btn" @click="actionOpen = false">取消</button>
      </div>
    </div>
  </div>
</template>
