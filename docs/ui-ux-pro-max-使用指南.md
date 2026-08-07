# UI UX Pro Max 使用指南

> 已安装到本项目 `.opencode/skills/` 目录，opencode 中提出 UI/UX 相关需求时会自动激活。

## 1. 它是什么

AI 技能（skill），内置可检索的设计数据库，为 AI 提供专业 UI/UX 设计智能：

- **84 种 UI 风格**（Glassmorphism、Neumorphism、Brutalism、Bento Grid、Dark Mode 等）
- **192 套行业配色**、**74 组字体搭配**、**25 种图表推荐**
- **161 条行业推理规则**（SaaS、金融、医疗、电商、美业等）
- **22 个技术栈规范**（React、Next.js、Vue、Tailwind、Flutter、JavaFX 等）
- **98 条 UX 规范**（最佳实践、反模式、无障碍）

## 2. 前提条件

- Python 3（本机已安装：`python 3.14.0`）
- Windows 上运行脚本用 `python` 而非 `python3`

## 3. 最简用法（推荐）

直接对 opencode 说，例如：

```
为我的比赛项目做一个 landing page
```

技能会自动执行完整流程：

1. 分析需求（产品类型、受众、风格、技术栈）
2. 生成设计系统（页面模式、风格、配色、字体、动效、反模式）
3. 补充检索 + 按你的技术栈输出代码
4. 交付前按检查清单自检

## 4. 手动运行搜索脚本

技能目录：`.opencode/skills/ui-ux-pro-max/`

### 4.1 生成设计系统（核心功能）

```powershell
# ASCII 输出（终端显示，默认）
python .opencode/skills/ui-ux-pro-max/scripts/search.py "SaaS dashboard" --design-system -p "项目名"

# Markdown 输出（适合写文档）
python .opencode/skills/ui-ux-pro-max/scripts/search.py "SaaS dashboard" --design-system -f markdown -p "项目名"

# JSON 完整输出（无截断）
python .opencode/skills/ui-ux-pro-max/scripts/search.py "SaaS" --domain style --json
```

输出包含：PATTERN（页面结构）、STYLE（风格）、COLORS（配色）、TYPOGRAPHY（字体）、KEY EFFECTS（动效）、AVOID（反模式）、PRE-DELIVERY CHECKLIST。

### 4.2 设计拨盘（可选微调）

```powershell
python .opencode/skills/ui-ux-pro-max/scripts/search.py "SaaS" --design-system --variance 8 --motion 7 --density 8
```

| 拨盘 | 低 (1-3) | 中 (4-7) | 高 (8-10) |
|------|----------|----------|-----------|
| `--variance` | 居中 / 极简 | 均衡 / 现代 | 大胆 / 非对称 |
| `--motion` | 微妙微交互 | 标准滚动动效 | 复杂编排（pin、Flip） |
| `--density` | 宽松（24-96px） | 标准（16-64px） | 紧凑仪表盘（8-32px） |

### 4.3 持久化设计系统（跨会话复用）

```powershell
# 保存到 design-system/MASTER.md
python .opencode/skills/ui-ux-pro-max/scripts/search.py "SaaS dashboard" --design-system --persist -p "MyApp"

# 页级覆盖：design-system/pages/dashboard.md
python .opencode/skills/ui-ux-pro-max/scripts/search.py "SaaS dashboard" --design-system --persist -p "MyApp" --page "dashboard"
```

生成结构：

```
design-system/
├── MASTER.md            # 全局设计规范（颜色/字体/间距/组件）
└── pages/
    └── dashboard.md     # 页面级覆盖（只写与 Master 不同的规则）
```

检索规则：建页面时先查 `pages/xxx.md`，存在则覆盖 Master；不存在则只用 Master。

### 4.4 领域检索（补充细节）

```powershell
python .opencode/skills/ui-ux-pro-max/scripts/search.py "关键词" --domain <领域>
```

| 领域 | 用途 | 示例 |
|------|------|------|
| `product` | 产品类型推荐 | `--domain product "SaaS enterprise"` |
| `style` | UI 风格 / 配色 / 效果 | `--domain style "glassmorphism dark"` |
| `color` | 配色方案 | `--domain color "fintech trust"` |
| `typography` | 字体搭配 | `--domain typography "elegant serif"` |
| `landing` | 落地页结构 / CTA | `--domain landing "hero social-proof"` |
| `chart` | 图表类型推荐 | `--domain chart "real-time dashboard"` |
| `ux` | UX 最佳实践 / 反模式 | `--domain ux "animation accessibility"` |
| `gsap` | GSAP 动效代码骨架 | `--domain gsap "scroll reveal"` |
| `react` | React/Next.js 性能 | `--domain react "memo rerender"` |
| `icons` | 图标推荐（含引入代码） | `--domain icons "navigation arrows"` |
| `google-fonts` | 单字体查询 | `--domain google-fonts "variable sans"` |

### 4.5 技术栈规范

```powershell
python .opencode/skills/ui-ux-pro-max/scripts/search.py "关键词" --stack <栈名>
```

可用栈：`react`、`nextjs`、`vue`、`svelte`、`astro`、`swiftui`、`react-native`、`flutter`、`nuxtjs`、`nuxt-ui`、`html-tailwind`、`shadcn`、`jetpack-compose`、`threejs`、`angular`、`laravel`、`javafx`、`wpf`、`winui`、`avalonia`、`uno`、`uwp`

示例：

```powershell
python .opencode/skills/ui-ux-pro-max/scripts/search.py "responsive layout" --stack html-tailwind
python .opencode/skills/ui-ux-pro-max/scripts/search.py "list performance navigation" --stack react
```

## 5. 完整工作流示例

**需求：** "做一个 AI 搜索工具的首页"

```powershell
# 1. 生成设计系统（必做）
python .opencode/skills/ui-ux-pro-max/scripts/search.py "AI search tool modern minimal" --design-system -p "AI Search"

# 2. 补充细节（按需）
python .opencode/skills/ui-ux-pro-max/scripts/search.py "minimalism dark mode" --domain style
python .opencode/skills/ui-ux-pro-max/scripts/search.py "search loading animation" --domain ux

# 3. 技术栈规范（按需）
python .opencode/skills/ui-ux-pro-max/scripts/search.py "list performance navigation" --stack react
```

然后让 opencode 综合以上结果实现页面。

## 6. 查询技巧

- **多维度关键词**：产品 + 行业 + 语气 + 密度组合，如 `"entertainment social vibrant content-dense"`，不要只写 `"app"`
- 同一需求换不同关键词再试：`"playful neon"` → `"vibrant dark"` → `"content-first minimal"`
- 先 `--design-system` 拿全量推荐，再用 `--domain` 深挖不确定的维度

## 7. 常用规则速查

| 事项 | 标准 |
|------|------|
| 图标 | 禁用 emoji 当图标，用矢量图标（Phosphor / Heroicons / Lucide） |
| 触摸目标 | iOS ≥44×44pt，Android ≥48×48dp |
| 微交互时长 | 150-300ms，平台原生缓动 |
| 文本对比度 | 正文 ≥4.5:1，暗色模式次要文本 ≥3:1 |
| 间距系统 | 统一 4/8dp 节奏 |
| 动效 | 尊重 `prefers-reduced-motion` |
| 响应式 | 375px / 768px / 1024px / 1440px |
| 状态 | 所有可点击元素 `cursor-pointer` + hover/focus 状态 |

## 8. 交付前自检

实现完成后提醒 opencode 执行：

- 无 emoji 图标、图标家族风格一致
- 触控区域达标、按压反馈清晰
- 明暗双模式对比度分别测试
- 键盘导航 focus 可见、无障碍标签完整
- 安全区 / 固定栏不遮挡内容
- 小屏（375px）与横屏验证

## 9. 维护

```powershell
uipro update            # 更新技能文件
uipro uninstall         # 卸载（自动检测平台）
```
