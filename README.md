# XAUUSD Local K-Line Debug System

🌐 语言 / Language: **简体中文** | [English](README.en.md)

本项目是一个本地策略调试平台：  
可视化回放 K 线、切换回测引擎、查看行为流、写评论、做统计复盘。

![系统主界面](preview/preview-frame.png)

<video src="preview/xauusd-local-kline-debug-system.mp4" controls width="100%"></video>

---

## 核心功能

- 引擎切换：在 `driver/` 中切换 `run_survival_v*_backtest.py`
- 数据切换：按 `Year / Month / Week / Day` 维度加载数据
- 图表调试：主览 + 缩略图 + 入场/平仓标记 + 交易连线
- 评论系统：单 K 评论、区间评论、批量提交、CSV 导出
- 复盘统计：操作次数、胜率、止盈止损、净收益等

![行为与标记示例](preview/preview-frame-mid.png)

---

## 30 秒快速开始

### macOS / Linux
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install pandas
cd debug_system
python3 server.py
```

浏览器打开：`http://127.0.0.1:8765/`

### 服务管理（推荐）
```bash
cd debug_system
python service_manager.py start
python service_manager.py status
python service_manager.py restart
python service_manager.py stop
```

### Windows (PowerShell)
```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install pandas
cd debug_system
python server.py
```

### Windows (CMD)
```cmd
python -m venv .venv
.venv\Scripts\activate.bat
pip install pandas
cd debug_system
python server.py
```

浏览器打开：`http://127.0.0.1:8765/`

---

## 使用流程（推荐）

1. 选择引擎：顶部引擎下拉，切换策略版本  
2. 选择数据：切换到某个年/月/周/日文件  
3. 看行为流：右侧查看入场、平仓、状态变化  
4. 加评论：点击 K 线或区间提交调试意见  
5. 看统计：底部统计面板对比策略效果  

---

## 目录说明

- `debug_system/`：Web 调试系统与本地服务
- `driver/`：Python 回测引擎（默认从这里读取）
- `Year/ Month/ Week/ Day/`：分层测试数据
- `preview/`：README 展示素材（截图与演示视频）

---

## 注意事项

- 本仓库不包含任何 `.mq5` 文件
- 新增策略时，按命名约定添加 `driver/run_survival_v*_backtest.py`
