<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import MarkdownIt from 'markdown-it'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  listArticles,
  getArticle,
  upsertArticle,
  createArticle,
  deleteArticle,
  type ArticleItem,
} from '@/api/articles'

const md = new MarkdownIt({ html: false, linkify: true })

const year = ref(new Date().getFullYear().toString())
const route = useRoute()

const articles = ref<ArticleItem[]>([])
const activeTitle = ref('')       // 当前编辑的文章标题（路径主键）
const titleInput = ref('')        // 标题输入框（可改名）
const dateInput = ref('')         // 文章日期 YYYY-MM-DD
const body = ref('')              // Markdown 正文
const dirty = ref(false)
const isNew = ref(false)
const loading = ref(false)
const saving = ref(false)
const viewMode = ref<'code' | 'preview'>('preview')

const rendered = computed(() => md.render(body.value))

async function loadList() {
  const res = await listArticles(year.value)
  articles.value = res.articles
}

async function openArticle(title: string) {
  if (dirty.value && !confirm('当前有未保存的修改，确定切换吗？')) return
  isNew.value = false
  activeTitle.value = title
  titleInput.value = title
  await loadContent(title)
}

async function loadContent(title: string) {
  loading.value = true
  try {
    const res = await getArticle(year.value, title)
    body.value = res.content
    dateInput.value = res.date || ''
    dirty.value = false
  } catch (e) {
    ElMessage.error('加载失败')
  } finally {
    loading.value = false
  }
}

function newArticle() {
  if (dirty.value && !confirm('当前有未保存的修改，确定新建吗？')) return
  isNew.value = true
  activeTitle.value = ''
  titleInput.value = ''
  dateInput.value = ''
  body.value = ''
  dirty.value = false
}

async function save() {
  const title = titleInput.value.trim()
  if (!title) {
    ElMessage.warning('请输入文章标题')
    return
  }
  saving.value = true
  try {
    const payload = { title, content: body.value, date: dateInput.value }
    if (isNew.value) {
      await createArticle(year.value, payload)
      ElMessage.success('已创建')
    } else {
      await upsertArticle(year.value, activeTitle.value, payload)
      ElMessage.success('已保存')
    }
    isNew.value = false
    activeTitle.value = title
    dirty.value = false
    await loadList()
  } catch (e) {
    ElMessage.error(e instanceof Error ? e.message : '保存失败')
  } finally {
    saving.value = false
  }
}

async function onDelete(title: string) {
  try {
    await ElMessageBox.confirm(`删除「${title}」？`, '确认删除', { type: 'warning' })
    await deleteArticle(year.value, title)
    ElMessage.success('已删除')
    if (activeTitle.value === title) {
      activeTitle.value = ''
      titleInput.value = ''
      dateInput.value = ''
      body.value = ''
      isNew.value = false
    }
    await loadList()
  } catch (e) {
    /* 取消 */
  }
}

function switchView() {
  viewMode.value = viewMode.value === 'code' ? 'preview' : 'code'
}

function onKeydown(e: KeyboardEvent) {
  if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 's') {
    e.preventDefault()
    save()
  }
}

const displayTitle = computed(() =>
  isNew.value ? '新建文章' : activeTitle.value || '未选择',
)

onMounted(async () => {
  // 支持从全局搜索跳转：?year=YYYY&title=标题
  const rq = route.query
  if (typeof rq.year === 'string') year.value = rq.year
  await loadList()
  const target = typeof rq.title === 'string' ? rq.title : null
  if (target && articles.value.some((a) => a.title === target)) {
    await openArticle(target)
  } else if (articles.value.length > 0) {
    await openArticle(articles.value[0].title)
  }
})
</script>

<template>
  <div class="articles" @keydown="onKeydown">
    <div class="articles-list">
      <div class="list-header">
        <span class="list-year">文章 · {{ year }}</span>
        <button class="btn-new" @click="newArticle">＋ 新建</button>
      </div>

      <ul class="article-list">
        <li v-if="articles.length === 0" class="empty-tip">还没有文章，点「新建」开始</li>
        <li
          v-for="a in articles"
          :key="a.title"
          class="article-item"
          :class="{ active: !isNew && a.title === activeTitle }"
          @click="openArticle(a.title)"
        >
          <span class="article-dot"></span>
          <span class="article-title">{{ a.title }}</span>
          <span v-if="a.date" class="article-date">{{ a.date }}</span>
          <button class="del-btn" @click.stop="onDelete(a.title)">✕</button>
        </li>
      </ul>
    </div>

    <div class="articles-editor">
      <div class="editor-head">
        <div class="editor-title">
          <input
            v-if="isNew"
            v-model="titleInput"
            class="title-input"
            placeholder="输入文章标题"
          />
          <span v-else class="date-label">{{ displayTitle }}</span>
          <span v-if="isNew" class="tag-new">新建</span>
          <input v-model="dateInput" type="date" class="date-input" title="文章日期" />
        </div>
        <div class="editor-actions">
          <span v-if="dirty" class="dirty-hint">未保存</span>
          <button class="btn-view" @click="switchView">
            {{ viewMode === 'code' ? '预览' : '编辑' }}
          </button>
          <button class="btn-save" :disabled="saving" @click="save">
            {{ saving ? '保存中…' : '保存' }}
          </button>
        </div>
      </div>

      <textarea
        v-if="viewMode === 'code'"
        v-model="body"
        class="editor-textarea"
        spellcheck="false"
        :placeholder="isNew ? '开始写作（Markdown）…' : ''"
        @input="dirty = true"
      ></textarea>
      <div v-else-if="!loading" class="md-body editor-preview" v-html="rendered"></div>
      <div v-else class="editor-loading">加载中…</div>
    </div>
  </div>
</template>
