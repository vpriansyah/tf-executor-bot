//+------------------------------------------------------------------+
//| CommandPoller.mq5                                                 |
//| EA kecil: polling command dari server bot (VPS Linux) lalu        |
//| eksekusi order di MT5. Jalan di terminal MT5 (Windows/VPS forex). |
//+------------------------------------------------------------------+
#property strict

input string ServerURL   = "https://vps-linux-anda.example.com/next-command";
input string AckURL      = "https://vps-linux-anda.example.com/ack";
input int    PollSeconds = 5;

datetime lastPoll = 0;

int OnInit()
  {
   EventSetTimer(PollSeconds);
   return(INIT_SUCCEEDED);
  }

void OnTimer()
  {
   string headers = "Content-Type: application/json\r\n";
   char   data[];
   char   result[];
   string resultHeaders;
   int    timeout = 5000;

   int res = WebRequest("GET", ServerURL, headers, timeout, data, result, resultHeaders);
   if(res == -1)
     {
      Print("WebRequest gagal, error: ", GetLastError(),
            " -- pastikan URL sudah di-whitelist di Tools > Options > Expert Advisors");
      return;
     }

   string response = CharArrayToString(result);
   if(StringLen(response) == 0 || response == "null")
      return; // tidak ada command menunggu

   // Format command dari server, contoh JSON sederhana:
   // {"id":"abc123","action":"BUY","symbol":"XAUUSD","lot":0.1,"sl":1945,"tp":1965}
   // Parsing JSON manual sederhana (untuk produksi, pakai library JSON MQL5 pihak ketiga)
   string cmdId   = ExtractField(response, "id");
   string action  = ExtractField(response, "action");
   string symbol  = ExtractField(response, "symbol");
   double lot     = StringToDouble(ExtractField(response, "lot"));
   double sl      = StringToDouble(ExtractField(response, "sl"));
   double tp      = StringToDouble(ExtractField(response, "tp"));

   bool ok = ExecuteCommand(action, symbol, lot, sl, tp);

   // Kirim balik acknowledgement supaya command tidak dieksekusi dobel
   string ackBody = StringFormat("{\"id\":\"%s\",\"status\":\"%s\"}",
                                  cmdId, ok ? "done" : "failed");
   char ackData[];
   StringToCharArray(ackBody, ackData);
   char ackResult[];
   string ackHeaders;
   WebRequest("POST", AckURL, headers, timeout, ackData, ackResult, ackHeaders);
  }

bool ExecuteCommand(string action, string symbol, double lot, double sl, double tp)
  {
   MqlTradeRequest request = {};
   MqlTradeResult  tradeResult = {};

   request.action   = TRADE_ACTION_DEAL;
   request.symbol   = symbol;
   request.volume   = lot;
   request.sl       = sl;
   request.tp       = tp;
   request.deviation= 20;
   request.magic    = 990001;
   request.comment  = "telegram-linux-bridge";

   if(action == "BUY")
     {
      request.type  = ORDER_TYPE_BUY;
      request.price = SymbolInfoDouble(symbol, SYMBOL_ASK);
     }
   else if(action == "SELL")
     {
      request.type  = ORDER_TYPE_SELL;
      request.price = SymbolInfoDouble(symbol, SYMBOL_BID);
     }
   else
     {
      Print("Action tidak dikenali: ", action);
      return false;
     }

   bool sent = OrderSend(request, tradeResult);
   Print("OrderSend result: retcode=", tradeResult.retcode, " ticket=", tradeResult.order);
   return sent && (tradeResult.retcode == TRADE_RETCODE_DONE);
  }

// Helper sederhana ambil value dari JSON flat (bukan parser JSON penuh)
string ExtractField(string json, string field)
  {
   string key = "\"" + field + "\":";
   int pos = StringFind(json, key);
   if(pos == -1) return "";
   pos += StringLen(key);
   int endPos = StringFind(json, ",", pos);
   int endBrace = StringFind(json, "}", pos);
   if(endBrace != -1 && (endPos == -1 || endBrace < endPos))
      endPos = endBrace;
   string value = StringSubstr(json, pos, endPos - pos);
   StringReplace(value, "\"", "");
   return value;
  }

void OnDeinit(const int reason)
  {
   EventKillTimer();
  }
