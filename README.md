# 清衡舆情分析平台 · 智能舆情监测与研判系统

面向企业品牌与公共事件的通用智能舆情分析平台：支持全网多源（社交媒体 / 新闻门户 / 短视频 / 行业论坛）内容监测与多模态解析，基于 NLP + 模拟 LLM 提供态势感知、情感识别、风险预警、传播溯源、观点聚类，并自动生成结构化研判报告与公关建议。内置语料不绑定任何特定行业或品牌，可一键替换为真实业务数据。

> 演示态使用**内置 JSON 模拟数据集** + **离线词典情感分析（jieba）** + **可一键替换的模拟 LLM 层**；生产环境可将模拟层替换为真实大模型 / 多模态服务，保持相同契约。

---

## 一、技术栈

- 后端：Python 3.13 · FastAPI · SSE（流式预警）· 自实现 HS256 JWT（零额外依赖）· RBAC
- 分析：jieba 分词 · SimHash 去重 · 情感/细粒度情绪 · Jaccard 观点聚类 · 传播父子链 · 实体共现图谱 · 烈度指数 S/A/B/C 分级
- 前端：原生 HTML/JS · 内置 ECharts（离线可跑，无需 CDN）· 内存令牌（不落 localStorage）
- 导出：reportlab 中文 PDF · Markdown · HTML

---

## 二、目录结构

```
Public Opinion/
├─ backend/
│  ├─ app/
│  │  ├─ main.py               # FastAPI 应用工厂（中间件/静态挂载/预热）
│  │  ├─ config.py             # 集中配置 + RBAC 权限矩阵 + 种子账号
│  │  ├─ security.py           # 自实现 JWT + pbkdf2 口令哈希 + RBAC 依赖
│  │  ├─ errors.py             # 规范化异常（{error:{code,message,request_id}}）
│  │  ├─ logging_utils.py      # 结构化 JSON 日志 + 请求 ID
│  │  ├─ models.py             # Pydantic 模型
│  │  ├─ data/                 # 数据集加载 / 清洗 / 多模态模拟
│  │  ├─ analysis/             # 认知分析引擎（情感/聚类/风险/溯源/报告）
│  │  ├─ services/             # 监测配置 / 预警引擎（SSE）
│  │  ├─ api/                  # REST 路由 + SSE 端点
│  │  └─ static/               # 前端（态势大盘/研判工作台/报告中心/监测配置）
│  ├─ data/dataset.json        # 模拟数据集（10 事件 / 1360 帖子）
│  ├─ requirements.txt
│  └─ .env.example
└─ data/
   ├─ mock/corpus_events.py     # 语料层：事件设定 + 事件专属细节/诉求/OCR/ASR 池
   ├─ mock/corpus_text.py       # 语料层：平台语体骨架 + 行业语境槽位 + 账号池
   ├─ mock/generate_mock.py     # 重新生成模拟数据集（固定随机种子，可复现）
   ├─ verify_corpus_realism.py  # 数据集真实度自查（27 项）
   └─ verify_emotion_chart.js   # 情绪分布图表链路回归
```

---

## 三、环境准备与启动

### 1. 准备 Python 虚拟环境并安装依赖

```bash
cd backend
python -m venv .venv
# Windows 激活：
.venv\Scripts\activate
# 安装依赖（fastapi / uvicorn / jieba / reportlab / pydantic）
pip install -r requirements.txt
```

### 2. （可选）重新生成模拟数据集

数据集 `backend/app/data/dataset.json` 已随项目提供（10 个事件、约 1360 条帖子，含 OCR/ASR/传播链，覆盖预付费服务纠纷、产品质量、虚假宣传、公共安全隐患、出行计费争议、在线服务宕机、理财收益争议、食品安全、公共便民服务与正面公益透明等典型议题）。
语料并非「模板填空」，而是按「事件专属细节 × 平台语体骨架」组合生成：微博是碎片抱怨、抖音是短句外放、
知乎是分点长文、新闻门户是记者报道体、论坛是从业者长贴，并带有真实的爆发-衰减时间曲线与幂律互动量。
如需重新生成（在**项目根目录**执行）：

```bash
python data/mock/generate_mock.py
```

生成后可跑真实度自查（校验文本可读性、跨事件串料、情感一致性、互动分布、时间分布等 27 项）：

```bash
python data/verify_corpus_realism.py
```

> 提示：项目虚拟环境（`backend/.venv`）中安装了 jieba，走语义分词；若用系统 Python 运行，
> 会回退到 n-gram 分词，去重条数会有 0.5% 以内的差异（两条路径都可用，报告口径以实际运行为准）。

### 3. 启动后端服务（同时托管前端）

```bash
cd backend
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --log-level info
```

启动后控制台出现 `分析引擎预热完成，服务就绪` 即表示数据已加载并计算完成。

### 4. 打开前端

浏览器访问 **http://localhost:8000** ，自动加载态势大盘，并使用下方演示账号登录。

> 说明：前端由后端同源托管，无需单独起静态服务器、无跨域问题。

---

## 四、演示账号（RBAC 三角色）

| 角色 | 账号 | 口令 | 权限范围 |
| --- | --- | --- | --- |
| 系统管理员 | `admin` | `admin123` | 全部：信源/阈值/通知配置、监测主题、研判、报告、预警、处置、公关 |
| 舆情分析师 | `analyst` | `analyst123` | 监测主题、查阅舆情、事件研判、生成/导出报告 |
| 公关运营人员 | `pr` | `pr123` | 接收预警、查看传播/观点、采纳公关建议、流转工单 |

> 生产环境请通过环境变量 `ADMIN_PASSWORD` 等覆盖口令，并接入真实用户库。

---

## 五、端到端演示：预付费门店闭店退费舆情

示例事件 `ev_g1`（某连锁健身品牌多门店闭店与预付卡退费纠纷）已内置并作为主演示事件，可直接演示完整闭环；同批还内置 `ev_g2`（家电质量隐患）、`ev_g3`（平台包赔虚假宣传）、`ev_g4`（公共安全隐患）、`ev_g5`（出行平台计费争议）、`ev_g6`（企业公益透明）、`ev_g7`（在线服务平台宕机与数据同步中断）、`ev_g8`（理财平台收益不及预期与赎回到账延迟）、`ev_g9`（食品品牌产品变质与标签不符）、`ev_g10`（城市公共便民服务预约难）共 9 个配套事件，覆盖服务纠纷、质量争议、合规风险、公共事件与正面评价等典型议题。主演示事件按真实舆情节奏构造：9 月 16 日上午出现首发帖，5 小时左右到达声量峰值，随后进入长尾，同时按昼夜节律分布（深夜声量最低）。

1. **登录** `analyst`（舆情分析师），进入「舆情态势大盘」查看总声量、情感分布、细粒度情绪分布、风险等级、实时预警滚动。
2. **监测流**：进入「舆情研判工作台 → 监测流」，按情感（负面）/信源/事件筛选，查看多模态卡片（含 OCR 图片解析、ASR 字幕）。
3. **事件研判**：点击 `ev_g1` 事件，查看传播时间线（首发/引爆节点）、核心观点聚类（6 簇）、实体共现图谱、原文 Top10。
4. **处置协同**：切换 `admin` 或 `pr`，流转处置状态（如「处理中」），填写处置备注与处置人；`pr` 可一键生成公关策略与回应话术草案。
5. **报告生成与导出**：进入「报告中心」，点击 `ev_g1` 生成专项研判报告（已预置对应口径公关策略与回应草案），预览后导出 **Markdown / HTML / PDF**（中文 PDF 由 reportlab 生成，含事件信息、传播态势、观点矩阵、风险结论、应对建议）。

---

## 六、报告导出说明

- 后端 `/api/reports/{event_id}/export?format=markdown|html|pdf`，鉴权需 `report:export`。
- 文件名含中文，已按 RFC 6266 使用 `filename*` UTF-8 编码 + ASCII 兜底，浏览器下载正常。

---

## 七、验收标准对照

| # | 验收项 | 对应实现 |
| --- | --- | --- |
| 1 | 配置监测主题与关键词并正确接入/模拟多源数据 | `/api/config/topics` + 内置 7 信源、10 事件、约 1360 帖模拟集（`generate_mock.py`，覆盖预付费、质量、合规、公共安全、计费、宕机、理财、食品、便民、公益等议题） |
| 2 | 多模态解析（图文 OCR / 音视频 ASR） | `data/multimodal.py` + `/api/ingest/demo` 管线演示（OCR/ASR 文本按事件专属，不会跨事件串料） |
| 3 | 内容清洗、SimHash 去重与观点聚类 | `data/clean.py`（SimHash/汉明距离）+ `analysis/cluster.py`（Jaccard 聚类），含约 14% 同质搬运样本 |
| 4 | 情感识别与细粒度情绪、风险 S/A/B/C 分级 | `analysis/sentiment.py` + `analysis/risk.py`（烈度指数），语料生成时按引擎口径校验情感一致性 |
| 5 | 传播溯源与实体关联 | `analysis/propagation.py`（首发/引爆/时间线）+ `analysis/entity_graph.py` |
| 6 | 预警触发（环比激增/敏感词/KOL） | `analysis/engine.py:_compute_alerts` + SSE `/api/stream/alerts` |
| 7 | 基于事件一键生成结构化研判报告并支持导出 | `/api/reports/generate` + 三种格式导出 |
| 8 | 完成至少一个完整事件监测→研判→处置→报告演示 | `ev_g1` 主演示事件端到端闭环（见第五节） |

---

## 八、已知限制 / 可替换项

- **LLM 层**：当前为离线模拟叙事与公关话术，设置 `USE_MOCK_LLM=false` 并配置 `LLM_API_KEY/LLM_BASE_URL/LLM_MODEL` 即可接入真实大模型（契约不变）。
- **多模态**：OCR/ASR 为模拟样本，接入真实服务时替换 `data/multimodal.py` 中解析函数即可。
- **鉴权**：演示态使用自实现 HS256 JWT；生产建议接入企业统一身份认证并妥善保管 `SECRET_KEY`。
- **持久化**：监测配置/处置状态落盘于 `backend/app/data/config_state.json`（JSON），生产可替换为数据库。
