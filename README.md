# Olist 经营分析 Agent

一个基于 Olist 巴西电商数据的可追溯问数助手。用户用自然语言提问，Agent 根据明确的指标口径查询本地 SQLite 数据，并展示回答和 SQL 依据。

[系统架构](docs/architecture.md) · [本地运行说明](docs/local_setup.md) · [评估报告](evaluation/results/regression_suite.json)

## 项目背景

固定主题的 BI 看板不容易回答临时业务问题。分析人员仍需理解指标定义、识别多表粒度并编写 SQL。本项目把这些步骤封装成一个受控的 Agent 流程，让用户提问后可以查看查询依据。

## 核心能力

- 使用 DeepSeek Tool Calling 选择指标目录、数据库结构和只读 SQL 工具。
- 将 Olist 的 9 张业务表装入本地 SQLite，并统一日期格式、建立常用关联字段索引。
- 使用只读连接、SQLite authorizer、查询超时和结果行数上限限制 SQL 访问。
- 保留多轮会话，并在网页中展示回答、工具调用和 SQL 依据。
- 提供自建业务问题集、标准 SQL、评估脚本和本地安全探针。

## 技术结构

| 目录 | 作用 |
| --- | --- |
| app | FastAPI 接口、Agent 编排、指标目录、SQL 安全层和网页界面 |
| scripts | CSV 入库和回归评估脚本 |
| evaluation | 基准问题、标准 SQL 和评估结果 |
| docs/architecture.md | 系统结构和一次请求的处理流程 |
| tests | 不调用模型 API 的本地单元测试 |

## 评估结果

| 检查项 | 当前记录 |
| --- | --- |
| 一轮业务问题 SQL 执行 | 19/19 |
| 至少一次工具查询结果与标准 SQL 匹配 | 19/19 |

19 条题目是自建基准。结果匹配的口径是每题至少一次成功的 SQL 工具结果与标准 SQL 投影一致；它不等同于最终回答的语义准确率。最终回答尚未经过系统化语义评测。详细记录见 [回归报告](evaluation/results/regression_suite.json)。

## 业务口径示例

- GMV 按 payments.payment_value 汇总；商品销售额按 order_items.price 汇总。
- 复购按 customer_unique_id 统计，至少两笔订单视为复购。
- 延迟率以已送达且具备完整时间字段的订单为范围。
- review_score 不高于 2 定义为差评。

## 本地运行

需要 Python 3.10 及以上版本、Olist CSV 数据和可用的 DeepSeek API 配置。首次安装、数据导入和启动步骤见[本地运行说明](docs/local_setup.md)。Windows 用户完成首次配置后，可双击项目根目录的 run.bat 启动页面。

## 数据来源

使用 [Olist Brazilian E-Commerce Public Dataset](https://www.kaggle.com/olistbr/brazilian-ecommerce)，该数据集页面标注许可为 CC BY-NC-SA 4.0。仓库仅包含项目代码、基准定义和评估文件；原始 CSV 与本地 SQLite 数据库不随项目发布。
