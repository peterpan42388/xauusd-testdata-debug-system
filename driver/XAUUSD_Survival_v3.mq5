// ============================================
// EA Name: XAUUSD_Survival_v3
// Role: K线图大师 & XAUUSD生存交易体
// Generated: 2026-05-08
// ============================================

#property copyright "Codex Generated"
#property link      "https://www.mql5.com"
#property version   "3.00"
#property strict
#property description "XAUUSD v3.0 生存结构交易: 结构准入 + 3级趋势 + 动量 + ATR风控 + 生存面板"

#include <Trade/Trade.mqh>

// -------------------- 核心常量（按需求固定） --------------------
const string SYMBOL_CONST          = "XAUUSD";
const int    Bollinger_Period      = 20;
const double Bollinger_Deviation   = 2.0;
const int    EMA_Fast              = 5;
const int    EMA_Slow              = 20;
const int    Trend_Big_Bars        = 50;
const int    Trend_Mid_Bars        = 25;
const int    Trend_Small_Bars      = 10;
const int    ATR_Period            = 14;
const double Risk_Per_Trade        = 0.01;   // 每笔最多风险账户1%

// 可调执行参数（不改变核心策略定义）
input group "========== 执行参数 ==========";
input long   InpMagicNumber        = 26050830;
input int    InpDeviationPoints    = 20;
input bool   InpEnableDebug        = true;
input bool   InpUseSymbolFilter    = true;   // true时只允许XAUUSD运行
input bool   InpStructRelaxedMode  = false;  // 默认严格结构；必要时可开启宽松回补做对照

// -------------------- 枚举定义 --------------------
enum ENUM_STATUS
{
   STATUS_FLAT  = 0,
   STATUS_SHORT = 1, // Sell
   STATUS_LONG  = 2  // Buy
};

enum ENUM_DIR
{
   DIR_DOWN = -1,
   DIR_FLAT = 0,
   DIR_UP   = 1
};

enum ENUM_LINE_CODE
{
   LINE_CODE_UP   = 0,
   LINE_CODE_DOWN = 1
};

enum ENUM_LINE_STATUS
{
   LINE_STATUS_SMOOTH = 0,
   LINE_STATUS_SHAKY  = 1
};

enum ENUM_SHAKY_LEVEL
{
   SHAKY_NONE   = 0,
   SHAKY_MEDIUM = 1, // >45
   SHAKY_HIGH   = 2  // >60
};

enum ENUM_BOLLING_STATUS
{
   BOLLING_NORMAL_EXPAND   = 0,
   BOLLING_NORMAL_CONTRACT = 1,
   BOLLING_CLIFF_UP        = 2,
   BOLLING_CLIFF_DOWN      = 3
};

enum ENUM_MOMENTUM
{
   MOMENTUM_STRONG_CONTINUE = 0,
   MOMENTUM_WEAK_CONTINUE   = 1,
   MOMENTUM_REVERSAL        = 2,
   MOMENTUM_UNCLEAR         = 3
};

CTrade trade;

int g_hBands = INVALID_HANDLE;
int g_hEma5  = INVALID_HANDLE;
int g_hEma20 = INVALID_HANDLE;
int g_hATR   = INVALID_HANDLE;

datetime g_lastBarTime = 0;

// 状态缓存
int g_status = STATUS_FLAT;
int g_lineCode = LINE_CODE_UP;
int g_lineStatus = LINE_STATUS_SMOOTH;
int g_shakyLevel = SHAKY_NONE;
int g_bollingStatus = BOLLING_NORMAL_CONTRACT;
int g_momentum = MOMENTUM_UNCLEAR;

int g_trendBigDir = DIR_FLAT;
int g_trendMidDir = DIR_FLAT;
int g_trendSmallDir = DIR_FLAT;

double g_trendBigAngle = 0.0;
double g_trendMidAngle = 0.0;
double g_trendSmallAngle = 0.0;
double g_bollingAngle = 0.0;

double g_stopPriceUp = 0.0;      // 空单止损
double g_stopPriceDown = 0.0;    // 多单止损
double g_takeProfitUp = 0.0;     // 空单止盈
double g_takeProfitDown = 0.0;   // 多单止盈

bool g_structUp = false;
bool g_structDown = false;
bool g_structXGold = false;
bool g_structXDead = false;
bool g_signUp = false;
bool g_signDown = false;
bool g_xGold = false;
bool g_xDead = false;

// 生存面板字段
string g_logs[5];
int    g_logCount = 0;
double g_peakBalance = 0.0;

void Dbg(const string msg)
{
   if(InpEnableDebug)
      Print("[DEBUG] ", msg);
}

void PushLog(const string msg)
{
   string stamped = TimeToString(TimeCurrent(), TIME_DATE|TIME_MINUTES) + " | " + msg;

   if(g_logCount < 5)
   {
      g_logs[g_logCount] = stamped;
      g_logCount++;
      return;
   }

   for(int i = 0; i < 4; ++i)
      g_logs[i] = g_logs[i + 1];

   g_logs[4] = stamped;
}

bool IsNewBar()
{
   datetime t0 = iTime(_Symbol, _Period, 0);
   if(t0 <= 0)
      return false;

   if(t0 != g_lastBarTime)
   {
      g_lastBarTime = t0;
      return true;
   }
   return false;
}

bool GetPosition(ulong &ticket, long &type, double &sl, double &tp, double &priceOpen, double &profit)
{
   for(int i = PositionsTotal() - 1; i >= 0; --i)
   {
      ulong t = PositionGetTicket(i);
      if(t == 0 || !PositionSelectByTicket(t))
         continue;

      if(PositionGetString(POSITION_SYMBOL) != _Symbol)
         continue;
      if(PositionGetInteger(POSITION_MAGIC) != InpMagicNumber)
         continue;

      ticket = t;
      type = PositionGetInteger(POSITION_TYPE);
      sl = PositionGetDouble(POSITION_SL);
      tp = PositionGetDouble(POSITION_TP);
      priceOpen = PositionGetDouble(POSITION_PRICE_OPEN);
      profit = PositionGetDouble(POSITION_PROFIT);
      return true;
   }
   return false;
}

void SyncStatus()
{
   ulong ticket = 0;
   long type = -1;
   double sl = 0.0, tp = 0.0, po = 0.0, pf = 0.0;

   if(!GetPosition(ticket, type, sl, tp, po, pf))
   {
      g_status = STATUS_FLAT;
      return;
   }

   if(type == POSITION_TYPE_SELL)
   {
      g_status = STATUS_SHORT;
      if(sl > 0.0) g_stopPriceUp = sl;
      if(tp > 0.0) g_takeProfitUp = tp;
   }
   else if(type == POSITION_TYPE_BUY)
   {
      g_status = STATUS_LONG;
      if(sl > 0.0) g_stopPriceDown = sl;
      if(tp > 0.0) g_takeProfitDown = tp;
   }
}

bool CloseCurrent(const string reason)
{
   ulong ticket = 0;
   long type = -1;
   double sl = 0.0, tp = 0.0, po = 0.0, pf = 0.0;

   if(!GetPosition(ticket, type, sl, tp, po, pf))
      return false;

   if(!trade.PositionClose(ticket))
   {
      Print("平仓失败, ticket=", ticket, ", retcode=", trade.ResultRetcode(), ", err=", GetLastError(), ", reason=", reason);
      return false;
   }

   string side = (type == POSITION_TYPE_BUY ? "平多" : "平空");
   PushLog(side + " | " + reason + " | PnL=" + DoubleToString(pf, 2));
   SyncStatus();
   return true;
}

double ToDeg(const double rad)
{
   return rad * 180.0 / M_PI;
}

int SignDir(const double x)
{
   if(x > 0.0) return DIR_UP;
   if(x < 0.0) return DIR_DOWN;
   return DIR_FLAT;
}

void ComputeTrend(const MqlRates &rates[], const int bars, int &dir, double &angleDeg)
{
   // 使用 bars 根已收盘K线的整体向量
   double y = rates[1].close - rates[bars].close;
   double x = (double)bars * _Point * 10.0;
   angleDeg = ToDeg(MathArctan2(y, x));
   dir = SignDir(y);
}

void ComputeLineStatus(const MqlRates &rates[], int &lineStatus, int &shakyLevel)
{
   lineStatus = LINE_STATUS_SMOOTH;
   shakyLevel = SHAKY_NONE;

   const int n = Trend_Small_Bars;
   const int points = n - 2; // 每3条均值

   double ma3[];
   ArrayResize(ma3, points);

   for(int i = 0; i < points; ++i)
   {
      int s1 = n - i;
      int s2 = n - i - 1;
      int s3 = n - i - 2;
      ma3[i] = (rates[s1].close + rates[s2].close + rates[s3].close) / 3.0;
   }

   int over30 = 0;
   double maxAbsAngle = 0.0;

   for(int j = 0; j < points - 1; ++j)
   {
      double dy = ma3[j + 1] - ma3[j];
      double dx = _Point * 10.0;
      double a = MathAbs(ToDeg(MathArctan2(dy, dx)));

      if(a > 30.0)
         over30++;

      if(a > maxAbsAngle)
         maxAbsAngle = a;
   }

   if(over30 >= 2)
      lineStatus = LINE_STATUS_SHAKY;

   if(lineStatus == LINE_STATUS_SHAKY)
   {
      if(maxAbsAngle > 60.0)
         shakyLevel = SHAKY_HIGH;
      else if(maxAbsAngle > 45.0)
         shakyLevel = SHAKY_MEDIUM;
      else
         shakyLevel = SHAKY_NONE;
   }
}

void ComputeBollingStatus(const double &upper[], const double &mid[], const double &lower[], int &status, double &angleDeg)
{
   double widthNow = upper[1] - lower[1];
   double widthPrev = upper[2] - lower[2];
   double widthDelta = widthNow - widthPrev;
   double midDelta = mid[1] - mid[2];

   // 角度按 (midDelta, widthDelta) 向量计算
   angleDeg = ToDeg(MathArctan2(midDelta, (widthDelta == 0.0 ? 0.0000001 : widthDelta)));

   bool expandRight = (widthDelta > 0.0);
   bool expandLeft  = (widthDelta < 0.0);

   if(expandRight && angleDeg > 90.0)
      status = BOLLING_CLIFF_UP;
   else if(expandLeft && angleDeg < -90.0)
      status = BOLLING_CLIFF_DOWN;
   else
      status = (widthDelta >= 0.0 ? BOLLING_NORMAL_EXPAND : BOLLING_NORMAL_CONTRACT);
}

bool IsSignUp(const MqlRates &rates[])
{
   return (rates[3].close < rates[2].close && rates[2].close < rates[1].close);
}

bool IsSignDown(const MqlRates &rates[])
{
   return (rates[3].close > rates[2].close && rates[2].close > rates[1].close);
}

void ComputeCross(const double &ema5[], const double &ema20[], bool &xGold, bool &xDead)
{
   xGold = (ema5[2] <= ema20[2] && ema5[1] > ema20[1]);
   xDead = (ema5[2] >= ema20[2] && ema5[1] < ema20[1]);
}

bool DetectStructUp(const MqlRates &rates[], const double &upper[])
{
   // left=3 mid=2 right=1
   // K_LINE_TOP        = high
   // K_LINE_PRICE_DOWN = min(open, close)
   int l = 3, m = 2, r = 1;

   double midTop = rates[m].high;
   double leftTop = rates[l].high;
   double rightTop = rates[r].high;
   double rightBodyDown = MathMin(rates[r].open, rates[r].close);
   double rightBottom = rates[r].low;
   double leftLow = rates[l].low;

   bool c1 = (midTop > upper[m]);
   bool c2 = (midTop > leftTop && midTop > rightTop);
   bool c3Strict = (rightBodyDown < leftLow);
   // 宽松回补：允许右侧下影线跌破左侧低点（视觉上常见“假跌破/扫流动性”）
   bool c3Relaxed = (rightBottom < leftLow);
   bool c3 = (c3Strict || (InpStructRelaxedMode && c3Relaxed));
   return (c1 && c2 && c3);
}

bool DetectStructDown(const MqlRates &rates[], const double &lower[])
{
   // left=3 mid=2 right=1
   // K_LINE_BOTTOM    = low
   // K_LINE_PRICE_UP  = max(open, close)
   int l = 3, m = 2, r = 1;

   double midBottom = rates[m].low;
   double leftBottom = rates[l].low;
   double rightBottom = rates[r].low;
   double rightBodyUp = MathMax(rates[r].open, rates[r].close);
   double rightTop = rates[r].high;
   double midBodyUp = MathMax(rates[m].open, rates[m].close);
   double midHigh = rates[m].high;

   bool c1 = (midBottom < lower[m]);
   bool c2 = (midBottom < leftBottom && midBottom < rightBottom);
   // 严格：右侧实体上沿突破中间K线顶部
   bool c3Strict = (rightBodyUp > midHigh);
   // 宽松回补：允许右侧上影线突破中间顶部，或右侧实体上沿高于中间实体上沿
   bool c3Relaxed = (rightTop > midHigh || rightBodyUp > midBodyUp);
   bool c3 = (c3Strict || (InpStructRelaxedMode && c3Relaxed));
   return (c1 && c2 && c3);
}

bool DetectStructXGold(const bool xGold, const double &ema5[], const double &ema20[], const double &mid[])
{
   if(!xGold)
      return false;

   double crossPoint = (ema5[1] + ema20[1]) / 2.0;
   return (crossPoint > mid[1]);
}

bool DetectStructXDead(const bool xDead, const double &ema5[], const double &ema20[], const double &mid[])
{
   if(!xDead)
      return false;

   double crossPoint = (ema5[1] + ema20[1]) / 2.0;
   return (crossPoint < mid[1]);
}

int CountSameDirection(const int a, const int b, const int c)
{
   int up = 0, down = 0;
   if(a == DIR_UP) up++; else if(a == DIR_DOWN) down++;
   if(b == DIR_UP) up++; else if(b == DIR_DOWN) down++;
   if(c == DIR_UP) up++; else if(c == DIR_DOWN) down++;

   return MathMax(up, down);
}

int ComputeMomentum(const int bigDir, const int midDir, const int smallDir, const int bollingStatus, const int lineStatus)
{
   int sameCount = CountSameDirection(bigDir, midDir, smallDir);
   bool allUp = (bigDir == DIR_UP && midDir == DIR_UP && smallDir == DIR_UP);
   bool allDown = (bigDir == DIR_DOWN && midDir == DIR_DOWN && smallDir == DIR_DOWN);

   bool bollMatchUp = (bollingStatus == BOLLING_CLIFF_UP || bollingStatus == BOLLING_NORMAL_EXPAND);
   bool bollMatchDown = (bollingStatus == BOLLING_CLIFF_DOWN || bollingStatus == BOLLING_NORMAL_EXPAND);

   if((allUp && bollMatchUp && lineStatus == LINE_STATUS_SMOOTH) ||
      (allDown && bollMatchDown && lineStatus == LINE_STATUS_SMOOTH))
      return MOMENTUM_STRONG_CONTINUE;

   if(sameCount >= 2)
      return MOMENTUM_WEAK_CONTINUE;

   // 背离：大趋势与小趋势相反
   if((bigDir == DIR_UP && smallDir == DIR_DOWN) || (bigDir == DIR_DOWN && smallDir == DIR_UP))
      return MOMENTUM_REVERSAL;

   return MOMENTUM_UNCLEAR;
}

void GetDynamicAtrMultipliers(const int momentum, const int lineStatus, const int bollingStatus, double &slMult, double &tpMult)
{
   // 1.5 ~ 2.5 ATR 止损，且至少 1:2.5 风报
   if(momentum == MOMENTUM_STRONG_CONTINUE)
   {
      slMult = 1.5;
      tpMult = 4.0;
   }
   else if(momentum == MOMENTUM_WEAK_CONTINUE)
   {
      slMult = 1.9;
      tpMult = 4.75;
   }
   else if(momentum == MOMENTUM_REVERSAL)
   {
      slMult = 2.5;
      tpMult = 6.25;
   }
   else
   {
      slMult = 2.2;
      tpMult = 5.5;
   }

   if(lineStatus == LINE_STATUS_SHAKY)
      slMult = MathMin(2.5, slMult + 0.2);

   if(bollingStatus == BOLLING_CLIFF_UP || bollingStatus == BOLLING_CLIFF_DOWN)
      slMult = MathMax(1.5, slMult - 0.1);

   tpMult = MathMax(tpMult, slMult * 2.5);
}

double NormalizeLot(double lot)
{
   double minLot = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MIN);
   double maxLot = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MAX);
   double step = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_STEP);

   lot = MathMax(minLot, MathMin(maxLot, lot));
   if(step > 0.0)
      lot = MathFloor(lot / step) * step;

   return NormalizeDouble(lot, 2);
}

double CalculateLotByRisk(const double stopDistance)
{
   if(stopDistance <= 0.0)
      return 0.0;

   double balance = AccountInfoDouble(ACCOUNT_BALANCE);
   double riskMoney = balance * Risk_Per_Trade;

   double tickValue = SymbolInfoDouble(_Symbol, SYMBOL_TRADE_TICK_VALUE_LOSS);
   if(tickValue <= 0.0)
      tickValue = SymbolInfoDouble(_Symbol, SYMBOL_TRADE_TICK_VALUE);

   double tickSize = SymbolInfoDouble(_Symbol, SYMBOL_TRADE_TICK_SIZE);
   if(tickValue <= 0.0 || tickSize <= 0.0)
      return 0.0;

   double moneyPerLot = (stopDistance / tickSize) * tickValue;
   if(moneyPerLot <= 0.0)
      return 0.0;

   double lots = riskMoney / moneyPerLot;
   return NormalizeLot(lots);
}

bool OpenShort(const double atr, const int momentum, const int lineStatus, const int bollingStatus, const string reason)
{
   double bid = SymbolInfoDouble(_Symbol, SYMBOL_BID);
   if(bid <= 0.0 || atr <= 0.0)
      return false;

   double slMult = 2.0, tpMult = 5.0;
   GetDynamicAtrMultipliers(momentum, lineStatus, bollingStatus, slMult, tpMult);

   double stopDist = atr * slMult;
   double takeDist = atr * tpMult;

   double sl = bid + stopDist;
   double tp = bid - takeDist;

   double lots = CalculateLotByRisk(stopDist);
   if(lots <= 0.0)
   {
      Dbg("开空失败: 风险仓位计算为0");
      return false;
   }

   if(!trade.Sell(lots, _Symbol, bid, sl, tp, reason))
   {
      Print("开空失败, retcode=", trade.ResultRetcode(), ", err=", GetLastError(), ", reason=", reason);
      return false;
   }

   g_stopPriceUp = sl;
   g_takeProfitUp = tp;
   SyncStatus();
   PushLog("开空 | " + reason + " | lots=" + DoubleToString(lots, 2));
   return true;
}

bool OpenLong(const double atr, const int momentum, const int lineStatus, const int bollingStatus, const string reason)
{
   double ask = SymbolInfoDouble(_Symbol, SYMBOL_ASK);
   if(ask <= 0.0 || atr <= 0.0)
      return false;

   double slMult = 2.0, tpMult = 5.0;
   GetDynamicAtrMultipliers(momentum, lineStatus, bollingStatus, slMult, tpMult);

   double stopDist = atr * slMult;
   double takeDist = atr * tpMult;

   double sl = ask - stopDist;
   double tp = ask + takeDist;

   double lots = CalculateLotByRisk(stopDist);
   if(lots <= 0.0)
   {
      Dbg("开多失败: 风险仓位计算为0");
      return false;
   }

   if(!trade.Buy(lots, _Symbol, ask, sl, tp, reason))
   {
      Print("开多失败, retcode=", trade.ResultRetcode(), ", err=", GetLastError(), ", reason=", reason);
      return false;
   }

   g_stopPriceDown = sl;
   g_takeProfitDown = tp;
   SyncStatus();
   PushLog("开多 | " + reason + " | lots=" + DoubleToString(lots, 2));
   return true;
}

bool TrailPositionByMomentum(const double atr)
{
   if(atr <= 0.0)
      return false;

   ulong ticket = 0;
   long type = -1;
   double sl = 0.0, tp = 0.0, openPrice = 0.0, profit = 0.0;
   if(!GetPosition(ticket, type, sl, tp, openPrice, profit))
      return false;

   if(g_momentum != MOMENTUM_STRONG_CONTINUE)
      return false;

   double slMult = 1.5, tpMult = 4.0;
   GetDynamicAtrMultipliers(g_momentum, g_lineStatus, g_bollingStatus, slMult, tpMult);

   bool needModify = false;
   double newSL = sl;
   double newTP = tp;

   if(type == POSITION_TYPE_BUY)
   {
      double ref = SymbolInfoDouble(_Symbol, SYMBOL_BID);
      double candSL = ref - atr * slMult;
      double candTP = ref + atr * tpMult;

      if(sl <= 0.0 || candSL > sl)
      {
         newSL = candSL;
         needModify = true;
      }
      if(tp <= 0.0 || candTP > tp)
      {
         newTP = candTP;
         needModify = true;
      }
   }
   else if(type == POSITION_TYPE_SELL)
   {
      double ref = SymbolInfoDouble(_Symbol, SYMBOL_ASK);
      double candSL = ref + atr * slMult;
      double candTP = ref - atr * tpMult;

      if(sl <= 0.0 || candSL < sl)
      {
         newSL = candSL;
         needModify = true;
      }
      if(tp <= 0.0 || candTP < tp)
      {
         newTP = candTP;
         needModify = true;
      }
   }

   if(!needModify)
      return false;

   if(!trade.PositionModify(ticket, newSL, newTP))
   {
      Print("更新SL/TP失败, ticket=", ticket, ", retcode=", trade.ResultRetcode(), ", err=", GetLastError());
      return false;
   }

   if(type == POSITION_TYPE_BUY)
   {
      g_stopPriceDown = newSL;
      g_takeProfitDown = newTP;
      PushLog("追踪多单SL/TP更新");
   }
   else
   {
      g_stopPriceUp = newSL;
      g_takeProfitUp = newTP;
      PushLog("追踪空单SL/TP更新");
   }

   return true;
}

string DirText(const int d)
{
   if(d == DIR_UP) return "UP";
   if(d == DIR_DOWN) return "DOWN";
   return "FLAT";
}

string LineStatusText(const int s)
{
   return (s == LINE_STATUS_SMOOTH ? "Smooth" : "Shaky");
}

string BollingStatusText(const int s)
{
   if(s == BOLLING_CLIFF_UP) return "Cliff_Up";
   if(s == BOLLING_CLIFF_DOWN) return "Cliff_Down";
   if(s == BOLLING_NORMAL_EXPAND) return "Normal_Expand";
   return "Normal_Contract";
}

string MomentumText(const int m)
{
   if(m == MOMENTUM_STRONG_CONTINUE) return "Strong_Continue";
   if(m == MOMENTUM_WEAK_CONTINUE) return "Weak_Continue";
   if(m == MOMENTUM_REVERSAL) return "Reversal";
   return "Unclear";
}

string StatusText(const int s)
{
   if(s == STATUS_SHORT) return "1 SHORT(Sell)";
   if(s == STATUS_LONG) return "2 LONG(Buy)";
   return "0 FLAT";
}

void RenderPanel()
{
   double bal = AccountInfoDouble(ACCOUNT_BALANCE);
   double eq = AccountInfoDouble(ACCOUNT_EQUITY);

   if(g_peakBalance <= 0.0)
      g_peakBalance = bal;
   g_peakBalance = MathMax(g_peakBalance, bal);

   double dd = (g_peakBalance > 0.0 ? (g_peakBalance - eq) / g_peakBalance : 0.0);
   dd = MathMax(0.0, dd);
   double hp = MathMax(0.0, 100.0 * (1.0 - dd));

   string logs = "";
   int start = MathMax(0, g_logCount - 5);
   for(int i = start; i < g_logCount; ++i)
   {
      logs += "\n" + g_logs[i];
   }

   string sStructUp = (g_structUp ? "true" : "false");
   string sStructDown = (g_structDown ? "true" : "false");
   string sStructXGold = (g_structXGold ? "true" : "false");
   string sStructXDead = (g_structXDead ? "true" : "false");

   string panel =
      "XAUUSD生存策略面板\n" +
      "STATUS: " + StatusText(g_status) +
      " | HP: " + DoubleToString(hp, 1) +
      " | SimBalance: " + DoubleToString(bal, 2) + "\n" +
      "TREND_BIG: " + DirText(g_trendBigDir) + " (" + DoubleToString(g_trendBigAngle, 1) + "°)" +
      " | TREND_MID: " + DirText(g_trendMidDir) + " (" + DoubleToString(g_trendMidAngle, 1) + "°)" +
      " | TREND_SMALL: " + DirText(g_trendSmallDir) + " (" + DoubleToString(g_trendSmallAngle, 1) + "°)\n" +
      "Bolling_Status: " + BollingStatusText(g_bollingStatus) + " (" + DoubleToString(g_bollingAngle, 1) + "°)" +
      " | LINE_STATUS: " + LineStatusText(g_lineStatus) +
      " | Momentum: " + MomentumText(g_momentum) + "\n" +
      "STRUCT: UP=" + sStructUp +
      " DOWN=" + sStructDown +
      " X_GOLD=" + sStructXGold +
      " X_DEAD=" + sStructXDead + "\n" +
      "STOP_UP=" + DoubleToString(g_stopPriceUp, _Digits) +
      " TP_UP=" + DoubleToString(g_takeProfitUp, _Digits) +
      " | STOP_DOWN=" + DoubleToString(g_stopPriceDown, _Digits) +
      " TP_DOWN=" + DoubleToString(g_takeProfitDown, _Digits) + "\n" +
      "交易日志(最近5笔):" + logs;

   Comment(panel);
}

int OnInit()
{
   if(InpUseSymbolFilter && _Symbol != SYMBOL_CONST)
   {
      Print("仅允许在 ", SYMBOL_CONST, " 图表运行。当前: ", _Symbol);
      return INIT_FAILED;
   }

   trade.SetExpertMagicNumber(InpMagicNumber);
   trade.SetTypeFillingBySymbol(_Symbol);
   trade.SetDeviationInPoints(InpDeviationPoints);

   g_hBands = iBands(_Symbol, _Period, Bollinger_Period, 0, Bollinger_Deviation, PRICE_CLOSE);
   g_hEma5  = iMA(_Symbol, _Period, EMA_Fast, 0, MODE_EMA, PRICE_CLOSE);
   g_hEma20 = iMA(_Symbol, _Period, EMA_Slow, 0, MODE_EMA, PRICE_CLOSE);
   g_hATR   = iATR(_Symbol, _Period, ATR_Period);

   if(g_hBands == INVALID_HANDLE || g_hEma5 == INVALID_HANDLE || g_hEma20 == INVALID_HANDLE || g_hATR == INVALID_HANDLE)
   {
      Print("初始化失败: 指标句柄无效, err=", GetLastError());
      return INIT_FAILED;
   }

   g_peakBalance = AccountInfoDouble(ACCOUNT_BALANCE);
   PushLog("EA启动");
   SyncStatus();
   RenderPanel();
   return INIT_SUCCEEDED;
}

void OnDeinit(const int reason)
{
   if(g_hBands != INVALID_HANDLE) IndicatorRelease(g_hBands);
   if(g_hEma5  != INVALID_HANDLE) IndicatorRelease(g_hEma5);
   if(g_hEma20 != INVALID_HANDLE) IndicatorRelease(g_hEma20);
   if(g_hATR   != INVALID_HANDLE) IndicatorRelease(g_hATR);

   Comment("");
}

void OnTick()
{
   if(!IsNewBar())
      return;

   const int needBars = 120;

   MqlRates rates[];
   double up[], mid[], down[], ema5[], ema20[], atr[];
   ArraySetAsSeries(rates, true);
   ArraySetAsSeries(up, true);
   ArraySetAsSeries(mid, true);
   ArraySetAsSeries(down, true);
   ArraySetAsSeries(ema5, true);
   ArraySetAsSeries(ema20, true);
   ArraySetAsSeries(atr, true);

   if(CopyRates(_Symbol, _Period, 0, needBars, rates) < 60)
      return;
   if(CopyBuffer(g_hBands, 0, 0, needBars, up) < 60 ||
      CopyBuffer(g_hBands, 1, 0, needBars, mid) < 60 ||
      CopyBuffer(g_hBands, 2, 0, needBars, down) < 60)
      return;
   if(CopyBuffer(g_hEma5, 0, 0, needBars, ema5) < 60 ||
      CopyBuffer(g_hEma20, 0, 0, needBars, ema20) < 60)
      return;
   if(CopyBuffer(g_hATR, 0, 0, needBars, atr) < 60)
      return;

   double atrNow = atr[1];
   if(atrNow <= 0.0)
      return;

   // 1) 更新所有状态
   SyncStatus();

   ComputeTrend(rates, Trend_Big_Bars, g_trendBigDir, g_trendBigAngle);
   ComputeTrend(rates, Trend_Mid_Bars, g_trendMidDir, g_trendMidAngle);
   ComputeTrend(rates, Trend_Small_Bars, g_trendSmallDir, g_trendSmallAngle);

   if(g_trendSmallDir == DIR_UP)
      g_lineCode = LINE_CODE_UP;
   else if(g_trendSmallDir == DIR_DOWN)
      g_lineCode = LINE_CODE_DOWN;

   ComputeLineStatus(rates, g_lineStatus, g_shakyLevel);
   ComputeBollingStatus(up, mid, down, g_bollingStatus, g_bollingAngle);

   g_signUp = IsSignUp(rates);
   g_signDown = IsSignDown(rates);

   ComputeCross(ema5, ema20, g_xGold, g_xDead);

   g_structUp = DetectStructUp(rates, up);
   g_structDown = DetectStructDown(rates, down);
   g_structXGold = DetectStructXGold(g_xGold, ema5, ema20, mid);
   g_structXDead = DetectStructXDead(g_xDead, ema5, ema20, mid);

   g_momentum = ComputeMomentum(g_trendBigDir, g_trendMidDir, g_trendSmallDir, g_bollingStatus, g_lineStatus);

   // 3) 持仓管理
   if(g_status == STATUS_SHORT)
   {
      if(g_xGold)
      {
         CloseCurrent("空单遇X_GOLD");
         RenderPanel();
         return;
      }

      if(g_momentum == MOMENTUM_REVERSAL || g_momentum == MOMENTUM_UNCLEAR)
      {
         CloseCurrent("空单动量反转/不明朗");
         RenderPanel();
         return;
      }

      TrailPositionByMomentum(atrNow);
      RenderPanel();
      return;
   }

   if(g_status == STATUS_LONG)
   {
      if(g_xDead)
      {
         CloseCurrent("多单遇X_DEAD");
         RenderPanel();
         return;
      }

      if(g_momentum == MOMENTUM_REVERSAL || g_momentum == MOMENTUM_UNCLEAR)
      {
         CloseCurrent("多单动量反转/不明朗");
         RenderPanel();
         return;
      }

      TrailPositionByMomentum(atrNow);
      RenderPanel();
      return;
   }

   // 2) 准入机制（仅结构触发开仓）
   if(g_status == STATUS_FLAT)
   {
      bool cliffUpCombo = (g_bollingStatus == BOLLING_CLIFF_UP && g_structUp && g_structXDead);
      bool cliffDownCombo = (g_bollingStatus == BOLLING_CLIFF_DOWN && g_structDown && g_structXGold);

      if(g_lineCode == LINE_CODE_UP)
      {
         if(g_structUp || g_structXDead || cliffUpCombo)
         {
            OpenShort(atrNow, g_momentum, g_lineStatus, g_bollingStatus, "STRUCT_UP_OR_X_DEAD");
            RenderPanel();
            return;
         }
      }
      else if(g_lineCode == LINE_CODE_DOWN)
      {
         if(g_structDown || g_structXGold || cliffDownCombo)
         {
            OpenLong(atrNow, g_momentum, g_lineStatus, g_bollingStatus, "STRUCT_DOWN_OR_X_GOLD");
            RenderPanel();
            return;
         }
      }
   }

   RenderPanel();
}
