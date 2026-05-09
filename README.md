# XAUUSD Local K-Line Debug System

一个本地可视化调试系统，用于回放 K 线、查看策略行为流、提交评论并切换回测引擎。

## 1. 安装

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install pandas
```

## 2. 启动

```bash
cd debug_system
python3 server.py
```

打开：`http://127.0.0.1:8765/`

## 3. 使用

1. 顶部选择 `引擎`（默认读取 `driver/` 下 `run_survival_v*_backtest.py`）。
2. 选择年/月/周/日数据文件并切换。
3. 在图表中点击 K 线写评论，右侧查看行为列表与统计。

## 4. 数据目录

- `Year/`：按年数据
- `Month/`：按月数据
- `Week/`：按周数据
- `Day/`：按日数据

已附带示例：`Week/Week_06_20260504_20260510.csv`

## 5. 说明

- 本仓库不包含任何 `.mq5` 文件。
- 如需接入新引擎，请在 `driver/` 增加 `run_survival_v*_backtest.py`。
