# 浏览器内置引擎 与 Python 后端 的数值一致性验证

> 背景：页面 `templates/index.html` 里内置了一份纯 JS 的电梯孪生引擎（复刻 CPython `random.Random`
> 的 MT19937 + mesa `RandomActivation` 的随机激活顺序），因此**在 Netlify 这类纯静态托管上也能完整跑出
> 仿真、出图、批量对比表**（后端不可达时自动降级，不报错、不空白）。
> 本目录存放「内置引擎与 Python 后端逐位一致」的验证脚本与留证截图。

## 一、结论

| 验证项 | 规模 | 结果 |
| --- | --- | --- |
| 固定用例（含边界：单人 / 满载 16 人 / 容量上限 / 意愿 0 与 1 等） | 27 组 | 全部逐字段一致 ✅ |
| 随机用例（含越界参数、2×2~50×30 网格、米制小数尺寸、steps 1~400、seed 0~1e9） | 60 组 | 全部逐字段一致 ✅ |
| 真实浏览器端到端（纯静态托管 / 同域 Flask / 跨域 `?api=`，各跑一次基础版 + 增强版 + 批量实验） | 3 场景 × 19 项 | 57/57 通过 ✅ |
| **线上真实站点**（Netlify 纯静态 `https://elevator-digital-twin.netlify.app/`，无后端可用） | 9 项 | 9/9 通过 ✅ |
| **后端探测 / 冷启动自愈**（未配置后端 / 地址不存在 / 后端迟启动 / 保存校验，各一个真实浏览器场景） | 4 场景 × 39 项 | 39/39 通过 ✅ |

比对字段：`metrics`（全部指标）、`grid`（每格状态与最近邻距离）、`frames`（逐帧快照文字网格）、
`floors` / `passengers`（增强版楼层与人数序列）、`unit`。曲线图是图片，不参与数值比对。

端到端额外核对了：引擎徽章自动判定、指标卡片文本、4×4/4×3 网格绘制、帧数标签、曲线图与对比图
（PNG dataURL）、批量对比表 15 行逐格数值、页面无 JS 报错。

## 二、文件清单

| 文件 | 说明 |
| --- | --- |
| `engine_cases.json` | 27 组固定用例（含边界与失败用例） |
| `engine_cases_rand.json` | 60 组随机/极端用例（`gen_rand_cases.py` 生成） |
| `gen_rand_cases.py` | 随机用例生成器（固定随机种子 20251014，可复现） |
| `engine_parity_py.py` | 用 Flask 测试客户端跑出 Python 后端的**标准答案** `engine_py_out*.json` |
| `engine_parity_js.js` | 从 `templates/index.html` 抽出内置引擎，在 Node 里跑同批用例并与标准答案**逐字段比对** |
| `e2e_page.py` | Playwright 真实浏览器端到端：静态托管降级 / 同域后端 / 跨域后端三场景 |
| `e2e_backend_probe.py` | Playwright 真实浏览器端到端：**后端探测 / 冷启动自愈 / 地址校验** 四场景（39 项） |
| `e2e_online.py` | Playwright **线上站点**冒烟：直接访问 Netlify 站点，校验降级、出图、出表、无报错 |
| `_e2e_*.png` | 三场景的整页截图（留证） |
| `live_netlify.png` | 线上 Netlify 站点的整页截图（留证） |

## 三、复现步骤

```powershell
# 0) 依赖：Python 3.11（Flask + mesa + matplotlib）、Node.js、（端到端需要）pip install playwright && playwright install chromium
cd <仓库根目录>

# 1) 数值一致性：固定 27 组 + 随机 60 组
python docs/offline_parity/engine_parity_py.py
node   docs/offline_parity/engine_parity_js.js

python docs/offline_parity/gen_rand_cases.py            # 重新生成 engine_cases_rand.json
$env:CASE_FILE='engine_cases_rand.json'
python docs/offline_parity/engine_parity_py.py
node   docs/offline_parity/engine_parity_js.js

# 2) 真实浏览器端到端（会临时起静态服务器与 Flask，跑完自动关闭）
python docs/offline_parity/e2e_page.py

# 2.5) 后端探测 / 冷启动自愈 / 地址校验（同样会临时起静态服务器，
#      并在「后端迟启动」场景里中途才拉起 Flask，最长约 1~2 分钟）
python docs/offline_parity/e2e_backend_probe.py

# 3) 线上站点冒烟（直接访问已部署的 Netlify 站点，需联网）
python docs/offline_parity/e2e_online.py
```

> **关于截图**：上面两个脚本**默认不截图、不写任何 PNG**（保持仓库干净）；
> 确需留图时显式加 `--shot`。提交用的证据截图请按 `截图指引.md` 自己截，
> 现成的 4 张 PNG（`_e2e_*.png`、`live_netlify.png`）是 2026-10-14 验证时留下的留证图。

预期输出末尾分别是：

```
全部 27 组：浏览器内置引擎与 Python 后端逐字段一致 ✅
全部 60 组：浏览器内置引擎与 Python 后端逐字段一致 ✅
===== 端到端验证：57/57 项通过 =====
全部通过 ✅
===== 后端探测验证：39/39 项通过 =====
全部通过 ✅
===== 线上站点冒烟：9/9 项通过 =====
全部通过 ✅
```

线上冒烟的具体结论（2026-10-14 实测，`live_netlify.png`）：

- 引擎徽章自动显示「浏览器内置引擎（离线）」——Netlify 上探测不到 `/api/*` 时正确降级；
- 基础版点一次「运行仿真」得到 `📏 1.104格 / 📐 1格 / ⚠️ 100.0% / 💬 3 交流对数`，**与 Python 后端 N1 用例逐字一致**；
- 增强版得到 `📏 0.533m / 📐 0.4m / ⚠️ 100.0% / 💬 2 / 👥 6人 / 🏢 6层`，同样与 Python 一致；
- 16 格网格（8 个乘客）、曲线图 PNG、帧标签「第 30 步」、批量实验表 15 行全部正常出图出表；
- 全流程 0 条 JS 报错。

## 四、后端探测与冷启动唤醒（为什么页面不会「永远离线」）

`templates/index.html` 里的 `probeBackend()` / `wakeBackend()` 是 2026-10-14 修掉的一个真坑：

- **旧行为**：只在页面加载时探一次 `/api/health`（5 秒超时），失败即把 `apiReady` 置为 `false`，
  而 `callEngine()` 里 `apiReady === false` 会直接短路到内置引擎 —— 于是一旦首次探测正好赶上
  Render 免费实例的冷启动（30~60 秒），页面**再也不会重试**，表现就是「明明部署了后端却一直显示离线」。
- **新行为**：探测结果区分四类原因（纯静态托管 / 超时 / 网络不可达 / 响应不像后端）；
  显式配置了后端地址时按 3s → 6s → 12s → 20s → 30s 退避重试（累计约 70 秒，覆盖冷启动），
  恢复后徽章自动切回「Python 后端引擎」并提示「冷启动唤醒用时约 X 秒」；
  仿真请求失败超过 15 秒也会自动复探一次。
- **纯静态托管不打扰**：没有配置后端地址时只探一次，不会反复打 404（`e2e_page.py` 断言 404 ≤ 2 条）。
- **地址规范化与校验**：`normalizeApiBase()` 自动补 `https://`（本机地址补 `http://`）、去掉末尾斜杠；
  文档里的示例占位符 `xxx.onrender.com` 会被识别并**拒绝保存**，非法地址给出内联提示且不静默刷新。

对应回归脚本：`python docs/offline_parity/e2e_backend_probe.py`（4 场景 39/39，见上表）。

## 五、内置引擎的几条关键口径（与 Python 对齐）

1. `random.Random(seed)`：完整复刻 CPython 的 MT19937 初始化、`random()`、`gauss()`、`shuffle()`、
   `choice()`；`gauss` 亦复刻 CPython 的 `gauss_next` 缓存行为（奇偶调用奇偶性不能错）。
2. `math.hypot` 不能用 —— V8 的 `Math.hypot` 不是正确舍入（与 CPython 差 1 ulp），改用
   `Math.sqrt(dx*dx + dy*dy)`，已用 0..40 全整数对穷举验证与 CPython `math.hypot` 完全一致。
3. 基础版指标保留 **2 位小数**（网格图里的最近邻距离）、末行指标 **3 位小数**，与 `webapp.py` 一致。
4. 参数裁剪口径同 `webapp._parse_params`（越界值夹取、`int()` 向零截断、非法值回落到默认值）。
5. 已知差异（仅报错文案）：增强版 `max_passengers` 超过轿厢格数时，Python 抛 `IndexError`（HTTP 500），
   内置引擎抛同义中文错误「乘客数 X 超过轿厢容量 Y」，避免弹出底层 `undefined` 报错。
