// ============================================
// CommonRiskGuard.mqh
// Shared risk guard loaded from driver/config/common_params.json
// ============================================
#ifndef __COMMON_RISK_GUARD_MQH__
#define __COMMON_RISK_GUARD_MQH__

#include <Trade/Trade.mqh>

CTrade g_rgTrade;

double g_rgInitialBalance = 0.0;
bool   g_rgDayBlocked = false;
string g_rgBlockReason = "";

double g_rgDailyMaxLossPct = 0.08;        // default: 8% of initial balance

double g_rgPerTradeMaxLossPct = 0.08;     // default: 8% of initial balance
int    g_rgDailyConsecLossLimit = 3;      // default: 3 consecutive losses

datetime g_rgDayStart = 0;

string RG_ExtractJsonValue(const string jsonText, const string key)
{
   string pat = "\"" + key + "\"";
   int p = StringFind(jsonText, pat);
   if(p < 0) return "";

   int colon = StringFind(jsonText, ":", p + StringLen(pat));
   if(colon < 0) return "";

   int start = colon + 1;
   int n = (int)StringLen(jsonText);
   while(start < n)
   {
      ushort c = StringGetCharacter(jsonText, start);
      if(c!=' ' && c!='\t' && c!='\r' && c!='\n') break;
      start++;
   }
   if(start >= n) return "";

   ushort ch = StringGetCharacter(jsonText, start);
   if(ch == '"')
   {
      int end = StringFind(jsonText, "\"", start + 1);
      if(end < 0) return "";
      return StringSubstr(jsonText, start + 1, end - (start + 1));
   }

   int endPos = start;
   while(endPos < n)
   {
      ushort cc = StringGetCharacter(jsonText, endPos);
      if(cc==',' || cc=='}' || cc=='\r' || cc=='\n') break;
      endPos++;
   }
   string raw = StringSubstr(jsonText, start, endPos - start);
   StringTrimLeft(raw);
   StringTrimRight(raw);
   return raw;
}

bool RG_LoadCommonParams()
{
   ResetLastError();
   int h = FileOpen("..\\..\\driver\\config\\common_params.json", FILE_READ | FILE_TXT | FILE_ANSI);
   if(h == INVALID_HANDLE)
   {
      Print("[RG] common_params.json not found, use defaults. err=", GetLastError());
      return false;
   }

   string json = "";
   while(!FileIsEnding(h))
      json += FileReadString(h);
   FileClose(h);

   if(StringLen(json) <= 0)
      return false;

   string v1 = RG_ExtractJsonValue(json, "daily_max_loss_pct");
   if(StringLen(v1) > 0)
      g_rgDailyMaxLossPct = MathMax(0.0, StrToDouble(v1));

   string v2 = RG_ExtractJsonValue(json, "per_trade_max_loss_pct");
   if(StringLen(v2) > 0)
      g_rgPerTradeMaxLossPct = MathMax(0.0, StrToDouble(v2));

   string v3 = RG_ExtractJsonValue(json, "daily_max_consecutive_losses");
   if(StringLen(v3) > 0)
      g_rgDailyConsecLossLimit = (int)MathMax(0, (int)StrToInteger(v3));

   return true;
}

double RG_DailyMaxLossAmount()
{
   return g_rgInitialBalance * g_rgDailyMaxLossPct;
}

double RG_PerTradeMaxLossAmount()
{
   return g_rgInitialBalance * g_rgPerTradeMaxLossPct;
}

datetime RG_TodayStart()
{
   return StringToTime(TimeToString(TimeCurrent(), TIME_DATE));
}

void RG_ResetForNewDayIfNeeded()
{
   datetime d = RG_TodayStart();
   if(g_rgDayStart != d)
   {
      g_rgDayStart = d;
      g_rgDayBlocked = false;
      g_rgBlockReason = "";
   }
}

void RG_RefreshDayState()
{
   RG_ResetForNewDayIfNeeded();

   double todayLossAbs = 0.0;
   int consecLoss = 0;
   double dailyLimitAbs = RG_DailyMaxLossAmount();

   datetime fromT = g_rgDayStart;
   datetime toT = TimeCurrent();
   if(!HistorySelect(fromT, toT))
      return;

   int total = (int)HistoryDealsTotal();
   for(int i=0; i<total; i++)
   {
      ulong deal = HistoryDealGetTicket(i);
      if(deal == 0) continue;

      string sym = HistoryDealGetString(deal, DEAL_SYMBOL);
      if(sym != _Symbol) continue;

      long entry = HistoryDealGetInteger(deal, DEAL_ENTRY);
      if(entry != DEAL_ENTRY_OUT) continue;

      long dtype = HistoryDealGetInteger(deal, DEAL_TYPE);
      if(dtype != DEAL_TYPE_BUY && dtype != DEAL_TYPE_SELL) continue;

      double profit = HistoryDealGetDouble(deal, DEAL_PROFIT)
                    + HistoryDealGetDouble(deal, DEAL_SWAP)
                    + HistoryDealGetDouble(deal, DEAL_COMMISSION);

      if(profit < 0.0)
      {
         todayLossAbs += -profit;
         consecLoss++;
      }
      else if(profit > 0.0)
      {
         consecLoss = 0;
      }
   }

   if(dailyLimitAbs > 0.0 && todayLossAbs >= dailyLimitAbs)
   {
      g_rgDayBlocked = true;
      g_rgBlockReason = "daily_max_loss";
      return;
   }

   if(g_rgDailyConsecLossLimit > 0 && consecLoss >= g_rgDailyConsecLossLimit)
   {
      g_rgDayBlocked = true;
      g_rgBlockReason = "daily_consecutive_losses";
      return;
   }

   g_rgDayBlocked = false;
   g_rgBlockReason = "";
}

void RG_EnforcePerTradeLoss()
{
   double maxLossAbs = RG_PerTradeMaxLossAmount();
   if(maxLossAbs <= 0.0)
      return;

   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      ulong ticket = PositionGetTicket(i);
      if(ticket == 0) continue;
      if(!PositionSelectByTicket(ticket)) continue;

      string sym = PositionGetString(POSITION_SYMBOL);
      if(sym != _Symbol) continue;

      double pnl = PositionGetDouble(POSITION_PROFIT)
                 + PositionGetDouble(POSITION_SWAP);
      if(pnl <= -maxLossAbs)
      {
         if(!g_rgTrade.PositionClose(ticket))
            Print("[RG] Force close failed ticket=", ticket, " err=", GetLastError());
         else
            Print("[RG] Force close by per_trade_max_loss ticket=", ticket, " pnl=", DoubleToString(pnl, 2));
      }
   }
}

bool RG_CanTradeToday()
{
   RG_RefreshDayState();
   return !g_rgDayBlocked;
}

string RG_StopReason()
{
   return g_rgBlockReason;
}

void RG_Init()
{
   g_rgInitialBalance = AccountInfoDouble(ACCOUNT_BALANCE);
   g_rgTrade.SetTypeFillingBySymbol(_Symbol);
   RG_LoadCommonParams();
   RG_RefreshDayState();

   Print("[RG] init balance=", DoubleToString(g_rgInitialBalance, 2),
         " daily_max_loss_pct=", DoubleToString(g_rgDailyMaxLossPct, 4),
         " per_trade_max_loss_pct=", DoubleToString(g_rgPerTradeMaxLossPct, 4),
         " daily_max_consecutive_losses=", g_rgDailyConsecLossLimit);
}

#endif
