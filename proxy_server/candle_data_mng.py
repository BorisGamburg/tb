import pandas as pd
import pandas_ta as ta
from pybit.unified_trading import HTTP, WebSocket
from datetime import datetime, timedelta
import threading
import time
from prog.proxy_server.shared_proxy import SharedProxy
from prog.drivers.bybit_driver import BybitDriver

class CandleDataMng:
    def __init__(self, symbol: str, timeframe: str, shared_proxy: SharedProxy):
        self.symbol = symbol.upper()
        self.tf = timeframe
        self.exchange_driver = shared_proxy.exchange_driver
        self.logger = shared_proxy.logger
        self.df = pd.DataFrame()
        self.last_update = datetime.now()
        self.needs_sync = False
        self.sync_lock = threading.Lock() 
        self.ws_client = None
        self.shared_proxy = shared_proxy
        self.fatal_error_msg = None

        # Состояние жизнеспособности
        self.last_heartbeat = time.time()
        self.max_delay = 60  # секунд до "смерти"

        self.last_full_sync = time.time()
        self.force_sync_interval = 3600 * 0.5  # Перезагружать историю каждые 30 мин

    def _ensure_data_ready(self):
        # Периодическая принудительная синхронизация
        if time.time() - self.last_full_sync > self.force_sync_interval:
            self.needs_sync = True
            self.last_full_sync = time.time()

        # Проверка фатальной ошибки
        if self.fatal_error_msg:
            raise Exception(f"Критический сбой в менеджере {self.symbol}: {self.fatal_error_msg}")

        # Проверка heartbeat
        if time.time() - self.last_heartbeat > self.max_delay:
            self.logger.warning(f"🚨 ДАННЫЕ ЗАСТЫЛИ ({self.symbol}).")       

    def _get_working_df(self):
        with self.sync_lock:

            if self.df.empty:
                self._load_history()
                self._start_websocket()

            elif self.needs_sync:
                self._load_history()
                self.needs_sync = False

            return self.df.copy()
        
    def _prepare_df(self):
        self.touch()
        self._ensure_data_ready()
        return self._get_working_df()
        
    def get_data(self):

        working_df = self._prepare_df()

        ha, rsi, bb = self._calculate_indicators(working_df)

        return self._format_data(working_df, ha, rsi, bb)
    
    def get_bb_ohlc(self):

        df = self._prepare_df().iloc[-100:]

        bb = ta.bbands(df["close"], length=20, std=2)

        return self._format_bb_ohlc(df, bb)
    
    def get_cci(self, length: int = 20):
        df = self._prepare_df().iloc[-100:].copy()
        
        # Вычисляем Typical Price вручную
        tp = (df["high"] + df["low"] + df["close"]) / 3
        
        # SMA от Typical Price
        sma_tp = tp.rolling(window=length).mean()
        
        # Mean Deviation (среднее абсолютное отклонение)
        mad = tp.rolling(window=length).apply(
            lambda x: sum(abs(x - x.mean())) / len(x), 
            raw=False
        )
        
        # Защита от деления на ноль
        mad = mad.replace(0, None).ffill().fillna(1e-8)
        
        # CCI с константой 0.015
        cci_series = (tp - sma_tp) / (0.015 * mad)
        
        # Ограничиваем выбросы
        cci_series = cci_series.clip(-500, 500)
        
        # Очистка
        cci_series = cci_series.replace([float('inf'), float('-inf')], 0.0).fillna(0.0)
        
        return self._format_cci(df, cci_series)

    def _format_bb_ohlc(self, df, bb_df):

        candles = [
            {
                "open": float(row["open"]),
                "high": float(row["high"]),
                "low": float(row["low"]),
                "close": float(row["close"]),
                "start": int(row["start"])
            }
            for _, row in df.iloc[-50:].iterrows()
        ]

        bb = [
            {
                "low": float(row.iloc[0]),
                "mid": float(row.iloc[1]),
                "high": float(row.iloc[2])
            }
            for _, row in bb_df.iloc[-50:].iterrows()
        ]

        return {
            "candles": candles,
            "bb": bb
        }
    
    def _format_cci(self, df, cci_series):

        last_closed_idx = -2
        prev_closed_idx = -3

        cci = float(cci_series.iloc[last_closed_idx])
        cci_prev = float(cci_series.iloc[prev_closed_idx])
        cci_slope = cci - cci_prev

        return {
            "cci": cci,
            "cci_slope": cci_slope
        }    

    def _load_history(self):
        # 1. Получаем сырые данные от драйвера
        raw_data = self.exchange_driver.get_kline_data(
            symbol=self.symbol, 
            interval=self.tf, 
            limit=200
        )

        if not raw_data:
            raise Exception(f"Empty data from API for {self.symbol}")

        # 2. Создаем DataFrame и приводим в порядок ТУТ
        df = pd.DataFrame(raw_data, columns=['start', 'open', 'high', 'low', 'close', 'volume', 'turnover'])
        df = df.astype(float)
        # Переворачиваем массив и сбрасываем индексы для корректной математики
        self.df = df[::-1].reset_index(drop=True)

        # Создаем колонку timestamp, чтобы _ws_callback не упал при первом сравнении
        self.df['timestamp'] = self.df['start']
        

    def _start_websocket(self):
        self.ws_client = WebSocket(testnet=False, channel_type="linear")
        self.ws_client.kline_stream(interval=int(self.tf), symbol=self.symbol, callback=self._ws_callback)

    def _ws_callback(self, msg):
        try:
            # Стучим в сердце при каждом сообщении
            self.last_heartbeat = time.time()
            
            if "data" not in msg or not msg["data"]:
                return
                
            k = msg['data'][0]
            start_ws = int(k['start'])
            ts_ws = int(k['timestamp'])

            with self.sync_lock:
                if self.df.empty:
                    self.needs_sync = True
                    return

                # Последние данные из DF
                last_row = self.df.iloc[-1]
                start_df = int(last_row['start'])
                ts_df = int(last_row.get('timestamp', 0))

                # Алгоритм обновления (start и timestamp)
                if start_ws == start_df:
                    if ts_ws >= ts_df:
                        self._update_row(k, ts_ws)
                        #print("Обновляем последнюю свечу")
                elif start_ws > start_df:
                    # Проверка на дырки и добавление
                    interval_ms = int(self.tf) * 60 * 1000
                    if start_ws > start_df + interval_ms:
                        self.needs_sync = True
                        #print("Нужен вызов API")
                    self._add_row(k, ts_ws)
                    #print("Добавляем свечу")
                    #print(self.df[-5:])
                elif start_ws < start_df:
                    self.needs_sync = True
                    #print("Нужен вызов API")

        except Exception as e:
            # Если мы тут, значит логика сломалась. Убиваем процесс.
            self.fatal_error_msg = str(e)
            self.shared_proxy.logger.error(f"❌ Критический сбой WS {self.symbol}: {e}")

    def touch(self):
        self.last_update = datetime.now()

    def is_stale(self, minutes=15):
        """Объект считается протухшим, если к нему не обращались 15 минут"""
        return datetime.now() - self.last_update > timedelta(minutes=minutes)  
      
    def stop(self):
        """Остановка радиостанции перед удалением объекта из реестра"""
        if self.ws_client:
            try:
                self.ws_client.exit() # Команда закрытия в pybit
            except:
                pass

    def _calculate_indicators(self, df):
        """Чистые расчеты без изменения основного self.df"""
        # 1. Heikin-Ashi
        ha = ta.ha(df['open'], df['high'], df['low'], df['close']).assign(start=df['start'])
        #ha = ta.ha(df['open'], df['high'], df['low'], df['close'])
        
        # 2. RSI
        rsi = ta.rsi(df['close'], length=14)
        
        # 3. Bollinger Bands
        bb = ta.bbands(df['close'], length=20, std=2) # type: ignore
        
        # Собираем результаты в один технический словарь
        return ha, rsi, bb
    
    def _format_data(self, df, ha_df, rsi_series, bb_df):
        """Только упаковка точных данных. Никакого округления."""
        # Индекс -1 — это живая свеча (игнорируем для разворота)
        # Индекс -2 — последняя ЗАКРЫТАЯ свеча
        # Индекс -3 — предпоследняя ЗАКРЫТАЯ свеча
        last_idx = -1
        last_closed_idx = -2
        prev_closed_idx = -3
        
        # Последняя закрытая HA свеча
        last_closed_ha = ha_df.iloc[last_closed_idx]
        # Предпоследняя закрытая HA свеча 
        prev_closed_ha = ha_df.iloc[prev_closed_idx]

        # BB для живой свечи
        last_bb = bb_df.iloc[last_idx]
        # BB для последней закрытой свечи 
        last_closed_bb = bb_df.iloc[last_closed_idx]

        return {
            "symbol": self.symbol,
            "last_price": float(df.iloc[last_idx]['close']),
            "rsi": float(rsi_series.iloc[last_idx]), # Чистая математика

            # BB для живой свечи
            "bb_low": float(last_bb.iloc[0]),
            "bb_mid": float(last_bb.iloc[1]),
            "bb_high": float(last_bb.iloc[2]),

            # BB для последней закрытой свечи
            "bb_low_last_closed": float(last_closed_bb.iloc[0]),
            "bb_mid_last_closed": float(last_closed_bb.iloc[1]),
            "bb_high_last_closed": float(last_closed_bb.iloc[2]),

            # Последняя закрытая HA свеча
            "curr_ha": {
                "HA_open": float(last_closed_ha['HA_open']), 
                "HA_close": float(last_closed_ha['HA_close']),
                "HA_low": float(last_closed_ha['HA_low']),   
                "HA_high": float(last_closed_ha['HA_high']),
                "HA_start": int(last_closed_ha['start'])
            },
            
            # Предпоследняя закрытая HA свеча
            "prev_ha": {
                "HA_open": float(prev_closed_ha['HA_open']), 
                "HA_close": float(prev_closed_ha['HA_close']),
                "HA_low": float(prev_closed_ha['HA_low']),   
                "HA_high": float(prev_closed_ha['HA_high']),
                "HA_start": int(prev_closed_ha['start'])
            }        
    }

    def _update_row(self, k, ts_ws):
        idx = self.df.index[-1]
        for key in ['open', 'high', 'low', 'close', 'volume', 'turnover']:
            self.df.at[idx, key] = float(k[key])
        self.df.at[idx, 'timestamp'] = ts_ws

    def _add_row(self, k, ts_ws):
        new_row = {
            'start': int(k['start']),
            'timestamp': ts_ws,
            'open': float(k['open']),
            'high': float(k['high']),
            'low': float(k['low']),
            'close': float(k['close']),
            'volume': float(k['volume']),
            'turnover': float(k['turnover'])
        }
        # Ограничиваем размер DF 200 строками
        self.df = pd.concat([self.df, pd.DataFrame([new_row])], ignore_index=True).iloc[-200:]

    def get_atr_ohlc(self, length: int = 14):
        """
        Возвращает OHLC свечи и значения ATR для указанного периода.
        :param length: Период для расчета ATR (по умолчанию 14).
        """
        # Нам нужно достаточно данных для расчета, поэтому берем с запасом
        # (минимум length + еще немного для стабилизации среднего значения)
        df = self._prepare_df().iloc[-(100 + length):]

        # Расчет ATR с динамическим периодом
        atr_series = ta.atr(df['high'], df['low'], df['close'], length=length)

        return self._format_atr_ohlc(df, atr_series)

    def _format_atr_ohlc(self, df, atr_series):
        """Форматирование OHLC и ATR в структуру для API/фронтенда"""
        # Берем последние 50 точек для выдачи (как в вашем примере с BB)
        candles = [
            {
                "open": float(row["open"]),
                "high": float(row["high"]),
                "low": float(row["low"]),
                "close": float(row["close"]),
                "start": int(row["start"])
            }
            for _, row in df.iloc[-50:].iterrows()
        ]

        # Значения ATR для тех же 50 свечей
        atr_values = [
            float(val) if pd.notna(val) else 0.0 
            for val in atr_series.iloc[-50:]
        ]

        return {
            "candles": candles,
            "atr": atr_values
        }
    
    def get_adx(self, length: int = 14):
        """
        Расчет индикатора ADX (Average Directional Index).
        Возвращает текущее значение ADX, +DI и -DI для последней закрытой свечи.
        """
        # Берем последние 100 свечей (для ADX нужно минимум 2*length для сглаживания)
        df = self._prepare_df().iloc[-100:].copy()
        
        # Расчет через pandas_ta
        # Возвращает DataFrame с колонками: ADX_14, DMP_14, DMN_14
        adx_df = ta.adx(df["high"], df["low"], df["close"], length=length)
        
        if adx_df is None or adx_df.empty:
            return {"adx": 0.0, "dmp": 0.0, "dmn": 0.0, "slope": 0.0}

        return self._format_adx(adx_df)

    def _format_adx(self, adx_df):
        """Форматирование данных ADX для передачи"""
        # Индекс -2 — последняя полностью закрытая свеча
        # Индекс -3 — свеча перед ней (для расчета наклона/динамики)
        last_closed_idx = -2
        prev_closed_idx = -3

        current_adx = float(adx_df.iloc[last_closed_idx, 0]) # ADX
        current_dmp = float(adx_df.iloc[last_closed_idx, 1]) # +DI
        current_dmn = float(adx_df.iloc[last_closed_idx, 2]) # -DI
        
        prev_adx = float(adx_df.iloc[prev_closed_idx, 0])
        adx_slope = current_adx - prev_adx

        return {
            "adx": current_adx,
            "dmp": current_dmp,
            "dmn": current_dmn,
            "adx_slope": adx_slope
        }    

    def get_ha(self):
        """
        Возвращает 3 последние HA свечи:
        [-3] предпоследняя закрытая
        [-2] последняя закрытая
        [-1] живая свеча
        """

        df = self._prepare_df().iloc[-100:].copy()

        ha_df = ta.ha(df["open"], df["high"], df["low"], df["close"]).assign(start=df["start"])

        last3 = ha_df.iloc[-3:]

        candles = []

        for _, row in last3.iterrows():

            ha_open = float(row["HA_open"])
            ha_close = float(row["HA_close"])

            if abs(ha_close - ha_open) < 1e-10:
                color = "doji"
            elif ha_close > ha_open:
                color = "green"
            else:
                color = "red"

            candles.append({
                "start": int(row["start"]),
                "HA_open": ha_open,
                "HA_close": ha_close,
                "HA_high": float(row["HA_high"]),
                "HA_low": float(row["HA_low"]),
                "color": color
            })

        return {
            "prev2": candles[0],   # -3
            "prev1": candles[1],   # -2
            "curr": candles[2]     # -1 (живая)
        }        
    
    def get_rsi(self, length: int = 14):
        """
        Возвращает RSI для последней закрытой свечи
        и его наклон (изменение относительно предыдущей).
        """

#        df = self._prepare_df().iloc[-100:].copy()
        df = self._prepare_df()

        rsi_series = ta.rsi(df["close"], length=length)

        return self._format_rsi(rsi_series)    
    
    def _format_rsi(self, rsi_series):

        curr_idx = -1
        last_closed_idx = -2
        prev_closed_idx = -3

        rsi_curr = float(rsi_series.iloc[curr_idx])
        rsi_last_closed = float(rsi_series.iloc[last_closed_idx])
        rsi_prev_closed = float(rsi_series.iloc[prev_closed_idx])

        return {
            "rsi_curr": rsi_curr,
            "rsi_last_closed": rsi_last_closed,
            "rsi_prev_closed": rsi_prev_closed
        }    
    
    def get_ema(self, length: int = 21):
        """
        Возвращает EMA:
        - текущее значение (живая свеча)
        - последняя закрытая
        - предыдущая закрытая
        - наклон EMA
        """

        df = self._prepare_df()

        ema_series = ta.ema(df["close"], length=length)

        return self._format_ema(ema_series)


    def _format_ema(self, ema_series):

        curr_idx = -1
        last_closed_idx = -2
        prev_closed_idx = -3

        ema_curr = float(ema_series.iloc[curr_idx])
        ema_last_closed = float(ema_series.iloc[last_closed_idx])
        ema_prev_closed = float(ema_series.iloc[prev_closed_idx])

        ema_slope = ema_last_closed - ema_prev_closed

        return {
            "ema_curr": ema_curr,
            "ema_last_closed": ema_last_closed,
            "ema_prev_closed": ema_prev_closed,
            "ema_slope": ema_slope
        }    
    
    def get_ohlc(self, n: int = 50):
        """
        Возвращает последние n OHLC свечей.
        Без расчета индикаторов.
        """

        df = self._prepare_df().iloc[-n:]

        candles = [
            {
                "open": float(row["open"]),
                "high": float(row["high"]),
                "low": float(row["low"]),
                "close": float(row["close"]),
                "start": int(row["start"])
            }
            for _, row in df.iterrows()
        ]

        return candles    