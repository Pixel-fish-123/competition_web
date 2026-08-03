# FRONTEND KNOWLEDGE BASE

**Scope:** `frontend/`（Vue3 + Vite + TS + Pinia + Element Plus）。页面职责见 `src/views/AGENTS.md`；根级全局配置见本文件。

## OVERVIEW
萌新杯前端：Vue3 `<script setup>` SFC + Vite + TypeScript + Pinia + Vue Router + Element Plus（zhCn 中文 locale），axios 走 Vite 代理到后端 :8000。

## STRUCTURE
```
frontend/
├── vite.config.ts          # dev 代理 /api 与 /ws(ws:true) → http://127.0.0.1:8000
├── tsconfig*.json          # 严格 lint（见 CONVENTIONS）
├── src/
│   ├── main.ts             # createApp + Pinia + Router + ElementPlus(zhCn)
│   ├── router/index.ts     # createWebHistory + 全局 beforeEach 守卫
│   ├── api/http.ts         # axios 单例，baseURL /api，401/403/429 拦截
│   ├── stores/auth.ts      # AuthUser + fetchMe/login/register/updateNickname/logout
│   ├── stores/index.ts     # 空占位（业务 store 未建）
│   ├── views/              # 页面（见 src/views/AGENTS.md）
│   └── plugins/triangle-occupy/  # 玩法前端组件（TriangleBoard/TriangleControls）
```

## ROUTING & GUARD
- `router/index.ts`：`createWebHistory()`；路由含 `/`、`/login`、`/competitions`、`/competitions/:cid`、`/competitions/:cid/matches/:mid`、`/rankings`、`/profile`（`meta.requiresAuth`）、`/admin`（AdminLayout + 5 子路由，redirect `/admin/users`）。
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
- **前端插件化半成品**：`MatchPlay.vue` 硬编码 `import { TriangleBoard, TriangleControls } from '../plugins/triangle-occupy'`，未按插件名动态解析组件；新增玩法需手改 MatchPlay。
- `stores/index.ts` 是空占位，业务 store 尚未建立。
- `Competitions.vue` 页面目前是空壳（仅标题），列表逻辑在 `Home.vue`。
- 代理仅 dev 生效；生产由后端托管 `frontend-dist/`（与 README 的 `frontend/dist` 需对齐，见根 AGENTS.md NOTES）。
