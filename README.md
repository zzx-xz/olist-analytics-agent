# Olist 经营分析 Agent

面向 Olist 巴西电商数据的可追溯分析助手。用户用自然语言提问，Agent 根据项目指标口径选择工具、查询本地数据，并返回结论和可核查的 SQL。

## 项目目标

原有 Power BI 看板适合浏览固定主题；临时问题仍需要分析人员理解多表关系、指标定义并编写 SQL。本项目尝试把这些能力封装为一个带边界的 AI Agent，同时保留查询依据，让回答可以复核。

## 当前功能

- 使用 DeepSeek Tool Calling 调用指标目录、数据库结构和只读 SQL 查询工具。
- 导入原项目的 9 张 Olist 表，覆盖 99,441 笔订单和约 100 万条地理位置记录。
- 入库时将多种日期字符串统一为 ISO 时间格式，保证 SQLite 日期筛选和按月汇总稳定。
- 使用单独的 SQLite 文件保存会话；支持延续上下文和恢复历史对话。
- SQL 通过只读连接和 SQLite authorizer 执行，设有超时和返回行数上限。
- 页面展示问题、回答、工具调用和 SQL；FastAPI 同时提供接口文档。
- 提供 19 条中文业务问题基准（12 条基础题、7 条进阶题），另设多轮追问与安全场景；按标准 SQL 核对工具查询结果，并统计执行率、匹配率、延迟和 Token 用量。

## 结构

| 目录或文件 | 用途 |
| --- | --- |
| app/agent.py | Tool Calling 循环、对话上下文和工具追踪 |
| app/data_store.py | 只读 SQL、安全限制和结果截断 |
| app/conversation_store.py | 独立保存会话与消息 |
| app/metrics.py | 指标语义目录 |
| app/static | 浏览器演示界面 |
| scripts/load_olist_csvs.py | 将原始 CSV 流式导入 SQLite |
| scripts/evaluate_agent.py | 执行基准评估并生成 JSON 报告 |
| scripts/evaluate_regression_suite.py | 顺序评估基础题与进阶题并汇总报告 |
| scripts/evaluate_scenarios.py | 评估多轮追问、破坏性请求与只读拦截 |
| evaluation/benchmark*.json | 中文问题及对应的标准 SQL |

## 本地运行

以下步骤适用于 Windows PowerShell。先进入项目根目录，再逐步执行。

### 1. 创建环境并安装依赖

```powershell
python --version
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

建议使用 Python 3.10 或更高版本。若当前 `python` 指向较旧版本，请先安装较新的 Python，再重开 PowerShell。

### 2. 配置模型 API

```powershell
Copy-Item .env.example .env
notepad .env
```

在 `.env` 中填写你自己的 `LLM_API_KEY`。默认地址和模型是 DeepSeek Chat Completions 与 `deepseek-flash`。不要把 `.env` 发到聊天或提交到 GitHub；`.gitignore` 已排除它。

### 3. 装载 Olist 数据

数据目录需要包含以下 9 个原始 CSV 文件（额外文件会被忽略）：

`olist_customers_dataset.csv`、`olist_geolocation_dataset.csv`、`olist_order_items_dataset.csv`、`olist_order_payments_dataset.csv`、`olist_order_reviews_dataset.csv`、`olist_orders_dataset.csv`、`olist_products_dataset.csv`、`olist_sellers_dataset.csv`、`product_category_name_translation.csv`。

把下面路径替换成你自己保存 Olist CSV 的目录：

```powershell
python scripts/load_olist_csvs.py --source "D:\path\to\olist-ecommerce-analysis\data"
```

如果 `data/olist.db` 已存在且内容正确，跳过此步即可。要从 CSV 重建数据库时，使用 `--replace`。

### 4. 启动并使用页面

首次配置完成后，日常启动可以直接双击项目根目录的 `run.bat`。它会启动本地服务并在服务就绪后打开网页；保持弹出的命令窗口打开即可使用，按 `Ctrl+C` 停止服务。如果服务已经运行，再双击会直接打开现有页面。

也可以在 PowerShell 里手动启动：

```powershell
uvicorn app.main:app --reload
```

手动启动后，在浏览器打开 <http://127.0.0.1:8000/health>，确认 `database_ready` 和 `model_configured` 都为 `true`，再打开 <http://127.0.0.1:8000/> 提问。健康检查只确认数据库文件存在、API 配置非空；它不会验证密钥有效或 DeepSeek 网络可达，提交一个简单问题才是完整连通性检查。可先试：

- `按项目口径，平台总 GMV 是多少？`
- `按州汇总 GMV，最高的 5 个州和金额分别是什么？`
- `按下单月份统计延迟送达率，最高的 5 个月是哪几个月？`
- 先问 `按州统计 GMV 排名第一的州和 GMV`，再追问 `那刚才这个州一共有多少个不同订单？`

展开“查看执行过程与 SQL 依据”可以检查 Agent 调用的工具和 SQL。浏览器会沿用当前会话；API 与页面都在本机运行。结束时回到服务窗口按 `Ctrl+C`。

## 评估

运行 `python scripts/evaluate_regression_suite.py` 会调用模型服务并产生 API 用量。模型 API 会收到问题、指标定义、查询结构和查询结果；原始 SQLite 数据库留在本地。报告写入 `evaluation/results/regression_suite.json` 及分组报告。运行 `python scripts/evaluate_scenarios.py` 会评估多轮追问和破坏性请求，也会调用模型。查看历史报告或重新比较已保存 SQL，使用带 `--rescore-existing` 的本地命令，不会调用模型。

当前提示词版本的一轮回归结果：基础题和进阶题共 19 题，SQL 执行率 100%（19/19），标准 SQL 结果匹配率 100%（19/19），中位响应时间 8.991 秒，总计 107,303 tokens。对标准结果投影出的 123 个字段值做回答文本提及检查，覆盖率为 100%（123/123）。另有多轮追问结果匹配 2/2、破坏性请求安全检查 1/1、本地只读拦截探针 5/5。

结果匹配率的口径是：每道题的 Agent 工具轨迹中，至少有一次成功的 SQL 查询结果与标准 SQL 投影一致。评测报告保留所有成功 SQL 尝试，并单独记录最后一次查询是否匹配。差评率题中 Agent 先取到了匹配标准结果的查询，随后又执行了一个辅助统计查询；因此该题匹配，但最后一次查询本身不匹配。回答提及检查只核对 123 个标准字段值是否出现在文本中，不判断解释、过滤条件或因果表述是否正确。19 题是自建小样本，不能外推到任意问题。

如果只调整了评测器或需要复核已保存 SQL，可运行 `python scripts/evaluate_regression_suite.py --rescore-existing`，在本地重新执行查询并对照标准 SQL，不会调用模型 API。多轮和安全报告也支持 `python scripts/evaluate_scenarios.py --rescore-existing`。

## 本地单元测试

运行 `python -m unittest discover -s tests -v` 可检查 SQL 只读限制、日期标准化和 Agent 的 SQL 失败重试上限；这组测试使用临时 SQLite 数据库和模拟模型响应，不会调用 DeepSeek。

## 指标口径

指标目录依据原 Olist 项目的 SQL 与访谈说明整理：

- GMV 使用 payments.payment_value 汇总；商品销售额使用 order_items.price，两者不混用。
- 复购按 customer_unique_id 统计用户订单数，至少 2 笔订单视为复购。
- 延迟率以 delivered 订单为范围，要求下单、实际送达和预计送达时间均存在。
- review_score 不高于 2 定义为差评。

## 后续迭代方向

1. 扩大基准集，加入跨批次重复运行和边界值测试，观察模型输出波动。
2. 将答案检查从数值提及扩展到语义一致性，并标记未被工具结果支持的句子。
3. 增加人工抽查记录、演示录屏和部署说明。

## 数据来源与 GitHub 发布

项目使用 [Olist Brazilian E-Commerce Public Dataset](https://www.kaggle.com/olistbr/brazilian-ecommerce)。Kaggle 页面标注数据集采用 CC BY-NC-SA 4.0；发布代码时请保留来源和许可说明，不要把原始 CSV 或生成的 SQLite 数据库上传到仓库。

建议把项目作为作品集公开到 GitHub：README、架构图、STAR、基准定义和评估报告能让面试官直接检查实现。提交前确认 `.env`、`.venv`、`data/olist.db`、原始数据和会话数据库都没有进入 Git。仓库目前尚未添加代码许可证；如果希望别人复用代码，应先选择许可证。没有许可证时，默认版权规则仍然适用。[GitHub 关于仓库许可的说明](https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/customizing-your-repository/licensing-a-repository)。
