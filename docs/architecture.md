# Agent 架构

```mermaid
flowchart LR
    U[用户问题] --> UI[浏览器界面]
    UI --> API[FastAPI]
    API <--> CS[(会话 SQLite)]
    API --> AG[Agent 编排器]
    AG <--> DS[DeepSeek Tool Calling]
    AG --> MC[指标语义目录]
    AG --> SC[表结构与关系目录]
    AG --> SG[只读 SQL 安全层]
    SG --> DB[(Olist SQLite)]
    SG --> AG
    AG --> API
    API --> UI
    UI --> E[回答与 SQL 依据]
    EV[19 条基准问题] --> AG
    EV --> GOLD[标准 SQL]
    AG --> REPORT[执行率 / 结果匹配 / 值提及 / 延迟 / Token 报告]
    GOLD --> REPORT
    SCN[多轮追问与安全场景] --> AG
    SCN --> SR[场景报告 / 本地拦截探针]
```

## 一次分析请求

1. 浏览器提交问题和可选的 session_id。
2. FastAPI 读取最近 8 条对话，传给 Agent。
3. Agent 根据问题选择业务指标、表结构和 SQL 工具。
4. SQL 安全层检查只读约束，限制执行时间和结果行数，再查询业务数据库。
5. 查询结果和工具调用记录回到 Agent，Agent 给出回答。
6. FastAPI 保存问答，并把回答和本次 SQL 轨迹返回浏览器。

分析数据文件与会话文件分开保存，Agent 只能使用只读数据库连接访问 Olist 表。
