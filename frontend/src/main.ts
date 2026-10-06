import { createApp, h } from 'vue'
// element-plus 按需引入。
// 原先 `import ElementPlus from 'element-plus'` + `app.use(ElementPlus)` 会全量注册
// 60+ 组件并把整套 CSS（约 455KB）打进主包；本项目实际只用到下面 4 个模板组件，
// 加上在 20+ 文件里被直接调用的 ElMessage / ElMessageBox 两个命令式 API。
// 各组件 style 入口会自动带上其依赖（如 dialog 会引入 base + overlay），可安全按需引入。
import { ElConfigProvider, ElDatePicker, ElDialog, ElDrawer, ElInput, ElInputNumber } from 'element-plus'
import zhCn from 'element-plus/es/locale/lang/zh-cn'
import 'element-plus/es/components/date-picker/style/css'
import 'element-plus/es/components/dialog/style/css'
import 'element-plus/es/components/drawer/style/css'
import 'element-plus/es/components/input/style/css'
import 'element-plus/es/components/input-number/style/css'
import 'element-plus/es/components/message/style/css'
import 'element-plus/es/components/message-box/style/css'
import App from './App.vue'
import router from './router'
import './styles/main.css'

const app = createApp({
  // 用 ElConfigProvider 包一层，保留中文 locale（日期选择器等依赖它）
  render: () => h(ElConfigProvider, { locale: zhCn }, () => h(App)),
})

for (const comp of [ElDatePicker, ElDialog, ElDrawer, ElInput, ElInputNumber]) {
  app.use(comp)
}
app.use(router)

app.mount('#app')
