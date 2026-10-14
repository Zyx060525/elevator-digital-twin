# 部署说明（可选）：Netlify 前端 + Render 后端

> 作品本身**本地即可完整运行**（见 `运行说明.md`），本文件只用于生成「在线体验链接」，
> 是提交表单里「在线体验链接 / 公开内容」一栏的加分项。
> 结构：前端静态站点部署到 **Netlify**，Flask 后端部署到 **Render**，通过 CORS 跨域连通。

---

## 一、部署架构

```
浏览器 ──> Netlify（静态前端 public/index.html，由 build_static.py 生成）
              │  ?api=https://<你的服务>.onrender.com
              └──> Render（Flask 后端：webapp.py，提供 /api/*）
```

前端页面通过 URL 参数 `?api=` 指定后端地址，例如：

```
https://你的站点.netlify.app/?api=https://你的服务.onrender.com
```

---

## 二、Render 后端部署

1. 新建 **Web Service** → 连接 GitHub/Gitee 仓库；
2. 环境（`render.yaml` 已声明默认值）：

| 项 | 值 |
|---|---|
| Environment | Python |
| Build Command | `pip install -r requirements.txt` |
| Start Command | `gunicorn webapp:app --bind 0.0.0.0:$PORT --timeout 120` |
| 环境变量 | `PYTHON_VERSION=3.11`（Render 需要 `3.11` 形式） |
| 可选环境变量 | `CORS_ORIGIN=https://你的站点.netlify.app`（收紧跨域） |

> 后端**不需要** Agnes Key 也能返回仿真结果；若要启用「Agnes 智能分析」，
> 在 Render 环境变量里加 `AGNES_API_KEY`（不要写进仓库）。

---

## 三、Netlify 前端部署

### 方式 A：导入 Git 仓库（推荐）

Netlify → Add new site → Import an existing project，表单四栏这样填：

| 字段 | 填写值 |
|---|---|
| Base directory | **留空** |
| Build command | `python build_static.py \|\| python3 build_static.py` |
| Publish directory | `public` |
| Functions directory | 留空 |

其余留默认。仓库里已有 `netlify.toml`，**配置文件优先于导入表单**，
即使表单留空也会按 `netlify.toml` 构建。

### 方式 B：手动拖拽

本地执行 `python build_static.py` 生成 `public/index.html`，把 `public/` 目录直接拖到 Netlify Drop。

---

## 四、常见坑（已踩过并修复）

| 现象 | 原因 | 处理 |
|---|---|---|
| `mise ERROR failed to install python-3.11.0` | 根目录 `runtime.txt` 内容 `python-3.11.0`（Render/Heroku 格式），Netlify 新镜像用 mise 只认纯版本号 `x.y` 且不能有 CRLF | **本项目已删除 `runtime.txt`**，Python 版本改用环境变量 `PYTHON_VERSION=3.11` 声明 |
| 构建成功但页面空白 | 发布目录填错 | Publish directory 必须是 `public`（`build_static.py` 的输出目录） |
| 页面能开、点击报「连不上后端」 | 前端与后端跨域/地址不对 | 访问时加 `?api=https://<Render 域名>`；后端已全局放行 CORS，可用 `CORS_ORIGIN` 收紧 |
| 首次请求很慢（>30s）、徽章长时间显示「浏览器内置引擎（离线）」 | Render 免费实例冷启动（30~60 秒） | **页面会自动退避重试唤醒（3s→6s→12s→20s→30s，累计约 70 秒），后端起来后徽章无需刷新自动变为「Python 后端引擎」并提示唤醒秒数**；也可先访问一次后端 `/api/health` 预热 |
| 填了后端地址点「保存」后仍提示离线 | 地址是文档里的示例占位符 / 格式不合法 | 页面会内联提示（占位符会被拒绝保存，非法地址提示「格式不对」）；请从 Render 控制台复制 Web Service 地址（形如 `https://xxx-xxx.onrender.com`）再保存 |

---

## 五、本地复现线上构建

```bash
cd 01_代码
python build_static.py     # 生成 public/index.html
# 用任意静态服务器打开 public/ 验证
```
