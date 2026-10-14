# 电梯场域数字孪生 —— 社交距离与交流行为多智能体仿真

> **一句话创意**：构建电梯微空间的多智能体数字孪生，模拟"人流—社交距离—交流行为"的
> 耦合演化，并经 AGH 完成"仿真—验证—现实"闭环，输出密闭空间治理与社交距离优化策略。

## 赛道
- **主赛道**：D. 工程设计与数字世界（数字孪生 + 系统建模与仿真）

## 技术栈
| 模块 | 技术 |
|---|---|
| 多智能体仿真 | Python 3.11 + MESA 2.x |
| 数字孪生建模 | 电梯轿厢网格化空间 + 乘客智能体 |
| AGH 能力调用接口 | MCP（Model Context Protocol） |

## 目录结构
```
elevator_twin/
├── __init__.py          # 包定义
├── model.py             # 基础版模型：Passenger + ElevatorModel + 指标
├── model_enhanced.py    # 增强版模型：真实尺寸 + 上下客 + 社会力
├── run.py               # 运行入口：单次演示 + 批量对比实验
├── mcp_server.py        # MCP 工具封装（供 AGH 调用）
├── agh_loop.py          # AGH 闭环演示（规划→调用→反馈→验证）
├── visualize.py         # 可视化：指标曲线 + 热力图 + 对比图
└── figs/                # 可视化输出（PNG）
webapp.py                # Web 前端（Flask 后端，浏览器访问 http://127.0.0.1:5000）
templates/
└── index.html           # 单页前端：参数面板 + 快照回放 + 批量实验 + Agnes 分析
docs/
└── 项目摘要与技术信息.md   # 提交材料模板
build_static.py          # 构建脚本：把 templates/index.html 复制到 public/（Netlify 发布目录）
netlify.toml             # Netlify 部署配置（静态前端）
render.yaml              # Render 部署配置（Flask 后端）
requirements.txt
```

## 环境要求
- Python 3.9+（已在 3.11 验证）

## 安装
```bash
pip install -r requirements.txt
```

## 运行
```bash
# 基础版：单次仿真演示 + 批量对比实验
python -m elevator_twin.run

# 增强版：真实尺寸(1.6m×1.4m) + 楼层上下客 + 社会力
python -m elevator_twin.model_enhanced

# 可视化：生成指标曲线 / 热力图 / 对比图（输出到 figs/）
python -m elevator_twin.visualize

# AGH 闭环演示：经 MCP 真实调用仿真工具，完成四步闭环
python -m elevator_twin.agh_loop

# Web 前端：浏览器打开 http://127.0.0.1:5000（参数调节 + 快照回放 + 批量实验 + Agnes 分析）
python webapp.py
```

## 部署

本项目是 Python(Flask) 服务：Netlify 的函数运行时只支持 JS/TS，**无法运行 Flask + mesa + matplotlib**，
因此采用「**前端上 Netlify、后端上 Render**」两段式部署，仓库里已备好 `netlify.toml` 与 `render.yaml`。

### 1. 后端：Render（提供 /api/* 接口）
1. Render → **New → Blueprint** → 选择本仓库，自动读取 `render.yaml`；
2. 在环境变量里填 `AGNES_API_KEY`（Agnes 官方 Key，**严禁提交进仓库**）；
3. 部署成功后记下地址，例如 `https://elevator-digital-twin.onrender.com`。

### 2. 前端：Netlify（托管静态单页）
导入本仓库时按下表填写（`netlify.toml` 内是同样的值，两边填一处即可）：

| 字段 | 填写内容 |
|---|---|
| Base directory | 留空（仓库根目录） |
| Build command | `python build_static.py` |
| Publish directory | `public` |
| Functions directory | 留空（本项目不使用 Netlify Functions） |

> `netlify.toml` 的构建命令带了 `\|\| python3 build_static.py` 兜底；本地也可直接执行：

```bash
python build_static.py   # 生成 public/index.html（public/ 已在 .gitignore 中忽略）
```

### 3. 让前端找到后端（跨域）
Netlify 域名与 Render 域名不同，需要指明后端地址，三种方式任选其一：
- **URL 参数**（最省事）：`https://<你的 Netlify 域名>/?api=https://<你的 Render 域名>`
- 页面里写死：在 `<head>` 内加 `<script>window.API_BASE='https://<你的 Render 域名>'</script>`
- 控制台设置一次：`localStorage.setItem('apiBase','https://<你的 Render 域名>')`

同域部署（例如直接访问 Render 的站点地址）时**无需任何配置**，前端自动请求同域 `/api/*`。

### 常见问题
- **Netlify 构建日志报 Python 版本错误**：仓库根目录的 `runtime.txt` 是 Render 格式（`python-3.11.0`）。
  删除该文件即可 —— `render.yaml` 里已用环境变量 `PYTHON_VERSION` 声明同一版本，Netlify 侧也在 `netlify.toml` 中指定。
- **页面能打开，但点按钮提示「连不上后端」**：静态前端找不到 Flask 后端，按上面第 3 步用 `?api=` 指定后端地址。
- **图表中文变方块**：后端需要 CJK 字体；`render.yaml` 里已 `apt-get install fonts-noto-cjk`，换平台请自行安装字体。

## MCP 集成（供 AGH 调用）
```bash
python -m elevator_twin.mcp_server
```
以 stdio 方式启动，暴露三个工具：
- `run_simulation`：运行一次仿真，返回关键指标
- `grid_snapshot`：返回空间快照，供人工核查
- `optimize_social_distance`：对比低/中/高三档交流意愿，输出策略建议

## 核心结论
批量实验（交流意愿 × 乘客数）清晰显示：
- 乘客数越多 → 平均最近邻距离越小、违规率越高（拥挤效应）；
- 交流意愿越高 → 交流对越多 → 平均距离进一步被压缩（**交流行为压缩社交距离**）。

示例（4×4 轿厢，30 步）：

| 乘客数 | 交流意愿 | 平均最近邻距离 | 违规率 | 交流对数 |
|---|---|---|---|---|
| 4 | 0.2 | 3.000 | 0.000 | 0 |
| 4 | 0.8 | 2.000 | 0.500 | 1 |
| 8 | 0.2 | 1.280 | 0.875 | 0 |
| 8 | 0.8 | 1.000 | 1.000 | 4 |

这为"密闭空间社交距离治理"提供了可计算的量化依据。

## 增强版核心洞察（真实物理尺寸）
增强版模型用真实电梯尺寸（默认 1.6m × 1.4m，网格粒度 0.4m）建模，并加入楼层上下客
动态与社会力移动。结果显示：即使乘客最大化距离，平均最近邻距离仍仅约 **0.47–0.80m**，
远小于 1.0m 的标准社交距离（违规率恒为 1.0）——证明**密闭空间社交距离在物理上不可达**，
而交流行为会在此基础上进一步压缩距离。
