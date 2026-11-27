# 本地运行

## 环境准备

建议使用 Python 3.10 或更高版本。在项目根目录打开 PowerShell，创建虚拟环境并安装依赖：

    python --version
    python -m venv .venv
    .\.venv\Scripts\Activate.ps1
    python -m pip install -r requirements.txt

首次运行前，将 .env.example 复制为本地 .env，并在其中配置 LLM_API_KEY。默认模型服务为 DeepSeek Chat Completions，模型名为 deepseek-flash。

## 准备 Olist 数据

从 [Olist 数据集页面](https://www.kaggle.com/olistbr/brazilian-ecommerce)获取 CSV 文件，将它们放在本机目录中。加载脚本使用以下 9 个文件：

- olist_customers_dataset.csv
- olist_geolocation_dataset.csv
- olist_order_items_dataset.csv
- olist_order_payments_dataset.csv
- olist_order_reviews_dataset.csv
- olist_orders_dataset.csv
- olist_products_dataset.csv
- olist_sellers_dataset.csv
- product_category_name_translation.csv

将下面命令中的目录替换为 CSV 所在位置：

    python scripts/load_olist_csvs.py --source "D:\path\to\olist-ecommerce-analysis\data"

成功导入后，数据库会生成在 data/olist.db。已有数据库时可以跳过导入；要从 CSV 重建时使用 --replace。

## 启动页面

Windows 用户可以双击项目根目录的 run.bat。命令窗口保持打开时服务持续运行，按 Ctrl+C 停止。也可以在已激活的虚拟环境中手动启动：

    python -m uvicorn app.main:app --reload

健康检查地址为 http://127.0.0.1:8000/health，页面地址为 http://127.0.0.1:8000/。健康检查只确认数据库文件存在、模型配置非空，不会验证 API 密钥是否有效或网络是否可达。

可以先尝试：

- 按项目口径，平台总 GMV 是多少？
- 按州汇总 GMV，最高的 5 个州和金额分别是什么？
- 按下单月份统计延迟送达率，最高的 5 个月是哪几个月？

## 评估与本地检查

运行回归评估会调用模型服务并产生 API 用量，模型 API 会收到问题、指标定义、查询结构和查询结果；原始 SQLite 数据库保留在本机。

    python scripts/evaluate_regression_suite.py

仅对已保存的 SQL 在本地重新执行并与标准 SQL 比较，不调用模型 API：

    python scripts/evaluate_regression_suite.py --rescore-existing

本地单元测试使用临时 SQLite 数据库和模拟模型响应，不会调用 DeepSeek：

    python -m unittest discover -s tests -v
