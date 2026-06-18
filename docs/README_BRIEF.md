# Brief: 重写 APoc 的 README.md

你的任务是为 `apoc/` 这个项目写一份**全新的、完整的、最新的 `README.md`**，替换 `apoc/README.md`。
这份 README 的双重读者是：(1) 想在 5 分钟内跑起来的开发者；(2) 在评估这个项目的**面试官 / 招聘方 / 开源访客**——所以它既是使用手册，也是一份"工程判断力的展示"。

不要凭空写。**先读代码、读出事实，再动笔。** 下面给出必须读的文件和必须讲清的故事。

---

## 第一步：先读这些文件（按顺序）

务必实际打开读，不要靠猜：

**后端 / 架构核心**
- `apoc/backend/app/graph/build.py` — 生成管线的图结构（这是项目的灵魂，DAG 的 fan-out/fan-in 注释要读懂）
- `apoc/backend/app/graph/nodes.py` — 每个节点做什么（research / candidate / judge / document / deck / reviews / persist），以及每个节点为什么用不同的模型和 reasoning effort
- `apoc/backend/app/config.py` — 所有设计决策的"配置化证据"：provider 选择逻辑、per-stage 模型分配、grounding 模式、角色定义、DOC_SECTIONS 从 10 合并到 7 的注释（这是一个很好的"为什么"故事）
- `apoc/backend/app/main.py` — 全部 API 路由（约 20 个），用来准确描述功能面
- `apoc/backend/app/research.py` + `apoc/backend/app/search.py` — SearXNG 发现 + Crawl4AI 抓取 + `[s1]` 引用的实现
- `apoc/backend/app/llm.py` + `apoc/backend/app/models.py` — provider-neutral 的抽象层

**前端**
- `apoc/frontend/src/ProjectView.tsx` — 主三栏审查视图
- `apoc/frontend/src/api.ts` — 前端调用的全部后端能力（功能清单的交叉验证）
- `apoc/frontend/src/` 下的组件名本身就是功能地图：`DiffView`、`CommentStatus`、`AnnotationMargin`、`MermaidLightbox`、`AiPanel`、`MarkdownDoc`、`Dashboard`

**已有上下文**
- 现有的 `apoc/README.md`（保留其中仍然正确的内容，尤其是产品定位、"为什么自托管 grounding"那三段、Run 部分；但要按下面的结构重组并补全最新功能）
- `apoc/docs/superpowers/plans/` 下若有计划文档可参考最近新增的功能（AI edit chat、diff view 等）

读的过程中，**核对现有 README 与代码是否已不一致**（例如默认端口、默认模型、env 变量名、新加的 AI 编辑/聊天功能），以代码为准。

---

## 第二步：README 必须包含的章节

按这个顺序，但措辞和小标题你自己润色，别机械照搬：

1. **一句话定位 + 一段电梯陈述**
   APoc 是什么、解决什么痛点（把早期架构对齐的"很多次会议"压缩成"一个可审计、可追溯的工作区"）。开门见山，别铺垫。

2. **截图 / 演示占位**
   留一个 `![screenshot](docs/...)` 占位和一句话说明放什么图（三栏审查视图 + 生成中的进度流）。注明"图待补"。

3. **核心功能（What it does）**
   用代码核对过的事实写 4–6 条：快速生成 POC（research→设计→可交互 HTML deck）、利益相关者审查报告 + 行级标注、GitHub 风格三栏审查、architect-only 编辑门禁 + approval roll-up、AI 编辑/聊天助手、全程 audit trail。每条一句话点出它对应的真实能力，不要营销空话。

4. **Quick Start（最重要的实操章节）**
   - 前置：Python 版本、Node 版本、Docker（可选，给 SearXNG）
   - 后端：venv → `pip install -r requirements.txt` → `crawl4ai-setup` → 设置 `DEEPSEEK_API_KEY` 或 `ANTHROPIC_API_KEY` → `./run.sh`（端口以代码为准，当前 8800）
   - 前端：`npm install` → `npm run dev`（端口以代码为准，当前 5174）
   - "最小可跑"路径：强调只要一个 API key 就能起（config.py 注释明说了这个设计意图）
   - 一个**60 秒 happy path**：打开页面 → 描述需求 → 看生成 → 进入审查 → approve。让读者知道跑起来之后该干嘛。

5. **架构（Architecture）— 重头戏**
   - 一张**生成管线图**：用 Mermaid 画 `research → {candidate_0, candidate_1} 并行 → judge → document → {deck, reviews} 并行 → persist`。这张图直接来自 `build.py`，必须准确。
   - 解释这是一个 **LangGraph StateGraph**，并说明 fan-out/fan-in 的意图（candidates 并行求广度，judge 收敛求质量，deck 与 reviews 因写不相交的 state key 所以并行）。
   - 技术栈表：后端 FastAPI + SQLite + LangGraph；前端 Vite + React 19 + TS + Tailwind v4；检索 SearXNG + Crawl4AI；deck 为自包含可编辑 HTML。
   - 数据/制品流：per-run artifacts 落在 `runs/`，POC/评论/审批/审计落在 SQLite。

6. **设计决策与取舍（Why it's built this way）— 项目的差异化亮点**
   这一节是给面试官看的。每条用"问题 → 选择 → 取舍"的结构，证据指向具体文件：
   - **Provider-neutral**：同一管线在 DeepSeek 和 Anthropic 上都能跑，per-stage 按"哪一步需要判别力"分配模型（DeepSeek V4 Pro 求广度，Opus 只用在 judge 等决定质量的步骤，Haiku 做第二候选）。证据：`config.py` 的 CANDIDATE_MODELS / JUDGE_MODEL 和 `nodes.py` 的 `_deepseek_reasoning_kwargs`（reasoning effort 按任务分级，deck 这种纯改写直接关掉 thinking 省延迟）。
   - **自托管 grounding 而非"让模型自己上网"**：可审计（每条主张带 `[s1]` 回溯真实 URL）、可控（自己掌握 query/数量/超时）、provider-neutral；一个 env var 即可切回 hosted。直接复用现有 README 那三段。
   - **DOC_SECTIONS 从 10 合并到 7**：因为独立调用时各 section 互相看不到输出、重复生成同一张 NFR 表/风险清单——合并既消重又减少串行调用。证据：`config.py` 里那段注释。这是"观察到具体浪费 → 针对性重构"的好例子。
   - **极简身份模型（DEMO_ALL_ADMIN）**：demo 里人人可扮演任意角色，但角色仍然存在，所以 architect-only 编辑门禁和 approval roll-up 仍可演示。说明这是"为 demo 刻意简化、但不牺牲可演示性"的取舍。
   - **legacy/graph 双生成路径**：`GENERATION_MODE` 让新管线灰度上线而不删旧代码——展示渐进式重构的纪律。

7. **展示的能力与思考（What this demonstrates）**
   一段短清单，直白点出这个项目作为作品集体现了什么：LLM 编排（LangGraph DAG、多候选+judge 的 fusion 模式）、成本/延迟工程（per-stage 模型与 reasoning 分级）、可审计 AI 系统设计（引用回溯 + audit trail）、provider 抽象、产品判断（明确的产品边界——只产出架构制品，不产出实现代码/IaC）、以及测试纪律（前端大量 `*.test.tsx`，后端 `tests/`）。
   语气要克制自信，陈述事实，不要自夸。

8. **配置（Configuration）**
   一张 env 变量表，从 `config.py` 抽取：`APOC_PROVIDER`、`DEEPSEEK_API_KEY`/`ANTHROPIC_API_KEY`、`APOC_GROUNDING`、`APOC_SEARXNG_URL`、`APOC_SEARCH_TOPK`、`APOC_CRAWL_*`、各 `APOC_FUSION_*` 模型覆盖、`APOC_GENERATION`、`APOC_DEMO_ALL_ADMIN` 等。每个给默认值和一句话用途。默认值必须和代码一致。

9. **项目结构（Project layout）**
   一个精简的目录树，只列有意义的目录，每行一句注释（backend/app、graph/、frontend/src、searxng/、skills/、runs/）。

10. **测试 / 开发**
    后端怎么跑测试、前端 `npm run test`（vitest）。

11. **产品边界 + 致谢**
    保留"只输出架构制品"的边界声明；保留对 frontend-slides / frontend-slides-editable 的 deck 灵感致谢。

---

## 风格与约束

- **语言**：英文（开源/求职场景，与现有 README 一致）。如另有要求再改中文。
- **长度**：充实但不啰嗦。架构和设计决策两节可以详细；Quick Start 要紧凑可执行。
- **事实优先**：每一个端口、默认模型、env 名、命令都必须和代码对得上。读到的与旧 README 冲突时以代码为准，并顺手改对。
- **Mermaid**：管线图用 Mermaid（仓库前端本来就渲染 mermaid，GitHub 也原生支持）。确保语法能渲染。
- **代码块**：所有命令给可复制的 fenced block，标注 `bash`。
- **不要发明功能**：只写代码里真实存在的能力。不确定的，回去读对应文件确认，别糊。
- **徽章/许可**：如仓库根有 LICENSE 就提一句；没有就跳过，别编。
- **语气**：工程师对工程师。自信、具体、克制。避免 "powerful / seamless / cutting-edge" 这类空词。

---

## 完成前自检

- [ ] 所有命令、端口、env 默认值都与 `config.py` / `run.sh` / `package.json` 一致
- [ ] 管线 Mermaid 图与 `build.py` 的边完全对应
- [ ] 每条"设计决策"都能指到一个具体文件作为证据
- [ ] 描述的每个功能都能在 `main.py` 路由或前端组件里找到对应
- [ ] 新功能（AI edit、chat、diff view、comment status）已纳入，没有遗漏
- [ ] 一个从没见过此项目的人，照着 Quick Start 能跑起来
