# EchoReview

面向短视频创作者的证据驱动复盘助手。系统通过固定流程采集视频指标与评论，清洗并提取评论信号，再结合可用数据生成流量复盘和创作建议。

## 工作流程

1. 获取视频指标。
2. 获取评论并记录采集数量。
3. 清洗评论并保留清洗统计。
4. 对非空的有效评论提取主题、情绪、观众问题和内容偏好。
5. 根据指标和评论洞察生成结构化复盘报告。
6. 根据报告生成创作建议。

必需步骤由 `app/core/review_workflow.py` 确定性编排，不依赖模型自行决定工具顺序。LLM 仅用于评论洞察、报告和建议生成。步骤返回 `error` 时流程停止，避免继续基于不完整数据产出结论；`partial` 数据会继续传递并在工具响应和 Trace 中保留状态。

工具的输入输出仍使用统一的 `ToolResponse`。流程会直接保存各步骤的结构化结果，CLI 和评测读取同一份流程结果，不再从对话上下文反向解析中间数据。`AgentRuntime` 保留为通用 Function Calling/ReAct 组件，但生产视频复盘路径不使用开放式 ReAct 调度。

## 当前能力与边界

- 支持从本地 Mock 数据复盘视频，以及通过 B 站公开接口获取视频指标和评论。
- 评论清洗包括去重、广告/噪音过滤和昵称脱敏。
- 评论洞察、流量报告和创作建议由配置的兼容 OpenAI Chat Completions API 的模型生成。
- 单次运行会输出 Markdown 报告；具备 B 站视频发布时间时，报告保存为 `reports/<BV号>-<YYYY-MM-DD>.md`。
- 单次运行 Trace 保存到 `traces/<run_id>.jsonl`，记录工具调用、状态、耗时、LLM 调用和最终报告。
- 当前版本不包含跨视频假设库或假设验证闭环。报告也不提供独立校准过的置信度分数；生成内容仍需结合原始数据人工核验。

## 本次重构对比

重构前，生产入口和评测入口都通过通用 ReAct Runtime 让模型决定“拉指标、拉评论、清洗、分析、报告、建议”的顺序，并从上下文消息反向提取中间结果。这样会产生重复调用、跳步、超过最大步数，以及结果提取依赖消息格式的问题。

重构后，`ReviewWorkflow` 固定编排六个业务步骤，按工具返回状态传递数据；错误立即停止，部分数据保留并披露。CLI 和评测共用这套编排，结构化结果直接进入报告、Markdown 落盘和评测结果。通用 `AgentRuntime` 仍保留，用于其它需要动态工具选择的场景，但不再承担本项目复盘主链路的必需顺序。

本次改动没有新增跨视频记忆、假设库、RAG、假设验证或独立置信度模型；这些属于后续功能，而不是本次职责重构。

## 环境配置

```powershell
python -m venv echo_venv
.\echo_venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
```

在 `.env` 中配置模型服务：

```dotenv
OPENAI_API_KEY=your-api-key
OPENAI_BASE_URL=https://api.openai.com/v1
OPENAI_MODEL=gpt-4o-mini
```

B 站公共接口不需要额外密钥。可按需配置 `BILIBILI_TIMEOUT` 与 `BILIBILI_USER_AGENT`。

## 运行

复盘 Mock 数据：

```powershell
python -m app.main "帮我复盘视频 video_001"
```

复盘 B 站视频：

```powershell
python -m app.main "帮我复盘 https://www.bilibili.com/video/BV1fNJQ6bEAj"
```

不传参数时进入交互模式。运行结束后终端显示报告和 Trace 路径；符合命名条件的 B 站报告另存到 `reports/`。

## 评测

运行全部标注数据：

```powershell
python -m eval.run_dataset --tag baseline
```

运行指定视频：

```powershell
python -m eval.run_dataset --tag smoke --videos eval_001 eval_002
```

评测结果写入 `data/eval/runs/<tag>.json`，单条运行 Trace 写入 `traces/`。评测通过相同的 `ReviewWorkflow` 执行流程，结果由结构化步骤返回值直接填充。具体质量指标以 `eval/metrics.py` 的当前实现为准。

## 项目结构

```text
app/
  core/review_workflow.py  固定流程编排与结构化结果汇总
  core/runtime.py          通用 Function Calling/ReAct Runtime
  platforms/bilibili.py    B 站公开数据 Provider
  tools/                   采集、清洗、分析、报告和建议工具
  main.py                  CLI、交互入口、报告保存和 Trace 保存
eval/                      数据集运行与结果评测
data/mock/                 本地 Mock 数据
data/eval/runs/            评测数据、标注和运行结果
reports/                   Markdown 复盘报告
traces/                    JSONL 单次运行 Trace
```
