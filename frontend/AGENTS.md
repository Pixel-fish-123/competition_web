# FRONTEND KNOWLEDGE BASE

**Scope:** `frontend/`（Vue3 + Vite + TS + Pinia + Element Plus）。页面职责见 `src/views/AGENTS.md`；根级全局配置见本文件。

## OVERVIEW
萌新杯前端：Vue3 `<script setup>` SFC + Vite + TypeScript + Pinia + Vue Router + Element Plus（zhCn 中文 locale），axios 走 Vite 代理到后端 :8000。

## STRUCTURE
```
frontend/
├── vite.config.ts          # dev 代理 /api 与 /ws(ws:true) → http://127.0.0.1:8000
│                           # port 5173 + strictPort（占用即报错，防"两个前端"假象，issue 2）
├── tsconfig*.json          # 严格 lint（见 CONVENTIONS）
├── src/
│   ├── main.ts             # createApp + Pinia + Router + ElementPlus(zhCn)
│   ├── router/index.ts     # createWebHistory + 全局 beforeEach 守卫（/admin/* 仅 admin；无 plugins 路由）
│   ├── api/http.ts         # axios 单例，baseURL /api，401/403/429 拦截
│   ├── stores/auth.ts      # AuthUser + fetchMe/login/register/updateNickname/logout
│   ├── views/              # 页面（见 src/views/AGENTS.md）
│   └── components/         # ScheduleChart.vue 等公共组件
```

## ROUTING & GUARD
- `router/index.ts`：`createWebHistory()`；路由含 `/`、`/login`、`/competitions`、`/competitions/:cid`、`/competitions/:cid/matches/:mid`、`/rankings`、`/profile`（`meta.requiresAuth`）、`/admin`（AdminLayout + 4 子路由：users/competitions/points/traffic，redirect `/admin/users`；玩法模块已删，issue 16）。
- 全局 `beforeEach`：先 `if (!auth.loaded) await auth.fetchMe()` 确保会话，再分流：
  - `/login` 且已登录 → 跳 `/`。
  - `to.path.startsWith('/admin')` 且 `role !== 'admin'` → 跳 `/`。
  - `meta.requiresAuth` 且未登录 → 跳 `/login?redirect=<fullPath>`。

## API LAYER
- `api/http.ts`：axios 单例，`baseURL: '/api'`、`withCredentials: true`（JWT httpOnly Cookie）。
- 响应拦截器：401 → 非 `/login` 时 `window.location.href = /login?redirect=...`；403 → `ElMessage.error('权限不足')`；429 → `ElMessage.error('请求过于频繁')`；其余 `Promise.reject`。
- `stores/auth.ts`：`AuthUser` 含 `nickname: string | null`；`fetchMe` 失败置 `user=null` 但 `loaded=true`；`register` 昵称选填（非空才发）；`updateNickname` PATCH `/auth/me`；`logout` finally 清空 user。getter `isRefereeOrAdmin`、`isLoggedIn`。

## CONVENTIONS
- tsconfig 严格 lint：`noUnusedLocals` / `noUnusedParameters` / `erasableSyntaxOnly` / `noFallthroughCasesInSwitch`（`tsconfig.app.json`）。
- **禁止 `as any` / `@ts-ignore`**——类型错误必须真修（根 AGENTS.md 反模式）。
- UI 文案统一中文；错误统一 `e?.response?.data?.detail` 展示。
- **无单元测试**，质量保障 = `npm run build`（`vue-tsc -b` + `vite build`）。

## TRAPS
- **阵营标注约定（用户确认）**：participant_a = 掠夺者（进攻方/attacker），participant_b = 守护者（防守方/defender）；页面统一标注「掠夺者 / 守护者」，不写红/蓝。
- `MatchPlay.vue` 对局判定流程：结束比赛 → 内联判定面板（导入日志自动判定 → 人工可微调 → 保存结果）→ POST /result `lock:true` 锁定；锁定后（`result_locked`）只读不可改（issue 14）。
- `Home.vue` 纯动图：轮播只播放动画，无任何交互按钮（issue 17）。
- `admin/Competitions.vue` 新建/编辑表单仅保留：名称/描述/头图URL/参赛形式（个人/混合）/赛制（瑞士/单败）/裁判/人数上限（issue 6）；删除按钮任意状态可用（issue 1）；进行中比赛有「强制结束」按钮（issue 8）。
- 代理仅 dev 生效；生产由后端托管 `frontend/dist`（main.py，SPA 深链回退 index.html）。
