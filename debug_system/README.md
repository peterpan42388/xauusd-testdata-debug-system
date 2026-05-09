# XAUUSD 本地K线调试系统

## 你现在可以做的事
1. 点击任意K线，弹出评论框（单K模式）
2. 切到区间模式，连续点击两根K线，弹出区间评论框
3. 评论先保存到“待提交”，右上角一次性批量提交
4. 图上可见评论标记 + 策略交易操作标记（开多/开空/平仓）
5. 导出评论 CSV

## 目录
- `server.py`：本地HTTP服务
- `build_ohlc_json.py`：把Excel转为OHLC JSON
- `generate_trades_json.py`：按策略离线回放生成交易操作标记
- `web/`：前端
- `data/ohlc.json`：K线数据
- `data/trades.json`：买多/买空/平仓标记数据
- `logs/comments.jsonl`：评论日志（JSONL）

## 启动
```bash
python3 /Users/leo/Menu/py_workspace/gold/TestData/debug_system/server.py
```
打开：
- http://127.0.0.1:8765

## 当你替换了测试Excel后
1. 生成K线数据
```bash
/Users/leo/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 \
  /Users/leo/Menu/py_workspace/gold/TestData/debug_system/build_ohlc_json.py
```
2. 生成交易标记
```bash
/Users/leo/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 \
  /Users/leo/Menu/py_workspace/gold/TestData/debug_system/generate_trades_json.py
```
3. 重启 `server.py`

## 评论接口
- `POST /api/comments`：单条评论
- `POST /api/comments/batch`：批量评论
- `GET /api/comments`：读取评论
- `GET /api/comments.csv`：导出CSV
