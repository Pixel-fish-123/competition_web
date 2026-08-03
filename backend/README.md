# 萌新杯音游比赛网站 — 后端

FastAPI + SQLAlchemy (SQLite) 后端。

## 开发环境启动

```powershell
cd D:\myproject1\competition_web\backend

# 1. 创建并激活虚拟环境（已存在则跳过）
python -m venv .venv
.venv\Scripts\activate

# 2. 安装依赖
pip install -r requirements.txt

# 3. （可选）初始化演示数据：admin + 裁判 + 8 名玩家 + 2 支队伍 + 1 场演示赛
#    幂等：重复运行不会产生重复数据
python seed.py

# 4. 启动后端
python -m uvicorn app.main:app --port 8000
```

## 前端启动

```powershell
cd D:\myproject1\competition_web\frontend
npm install
npm run dev
# 浏览器打开 http://localhost:5173 （CORS 已允许 5173）
```

## 运行测试

```powershell
cd D:\myproject1\competition_web\backend
.venv\Scripts\python -m pytest tests -q
```

## 种子数据与默认密码（仅限开发环境！）

`python seed.py` 会创建以下演示账号，全部使用默认弱口令：

| 账号 | 密码 | 角色 |
| --- | --- | --- |
| `admin` | `admin123` | 管理员 |
| `referee` | `referee123` | 裁判 |
| `player1` ~ `player8` | `player123` | 玩家 |

> ⚠️ **警告：以上默认密码仅供本地开发使用。**
> 生产 / 公网部署前必须修改或删除这些种子账号，切勿保留默认口令。

种子脚本额外创建：`萌新队A`（player1/2/3，队长 player1）、`萌新队B`
（player4/5/6，队长 player4）两支 3 人队伍，以及演示比赛
`萌新杯·演示赛`（round_robin + triangle_occupy，4 条已通过报名）。

脚本幂等：以用户名 `admin` 是否已存在为判断依据，已初始化时直接打印
`已初始化，跳过` 退出，不会产生重复数据。
