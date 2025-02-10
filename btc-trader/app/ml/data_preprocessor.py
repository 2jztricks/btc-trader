# File: app/ml/data_preprocessor.py

import pandas as pd
import numpy as np
from sklearn.preprocessing import MinMaxScaler
from structlog import get_logger

logger = get_logger(__name__)

class DataPreprocessor:
    def __init__(self, lookback=60, prediction_window=5):
        self.lookback = lookback
        self.prediction_window = prediction_window
        self.scaler = MinMaxScaler(feature_range=(0, 1))

        # For 1m base: open_1m, close_1m, etc.
        self.base_1m = ['open_1m', 'high_1m', 'low_1m', 'close_1m', 'volume_1m']
        # For 5m base
        self.base_5m = ['open_5m', 'high_5m', 'low_5m', 'close_5m', 'volume_5m']

        # Indicators for 1m
        self.indicators_1m = [
            'rsi_1m', 'macd_1m', 'signal_1m', 'upper_band_1m', 'lower_band_1m',
            'ema9_1m', 'ema21_1m', 'ema55_1m'
        ]
        # Indicators for 5m
        self.indicators_5m = [
            'ema9_5m', 'ema21_5m', 'ema55_5m', 'rsi_5m', 'macd_5m', 'signal_5m'
        ]

        # Full list of required columns
        self.required_columns = self.base_1m + self.base_5m + self.indicators_1m + self.indicators_5m

    def merge_timeframes(self, df1m, df5m):
        """
        Merge 1m & 5m data on their time index (both named 'bucket').
        We'll do a left join on the 1m index, then forward-fill 5m.
        """
        df = df1m.join(df5m, how='left')  # left join to keep all 1m rows
        # Forward fill the 5m columns so intermediate 1m rows have the same 5m data
        df.ffill(inplace=True)
        return df

    def create_features_for_1m(self, df):
        """
        Calculate indicators for the 1-minute columns only.
        Expect columns: open_1m, close_1m, etc.
        """
        if df.empty:
            return
        # Basic checks
        needed_1m = ['open_1m', 'high_1m', 'low_1m', 'close_1m', 'volume_1m']
        if not all(c in df.columns for c in needed_1m):
            logger.warning("Missing 1m columns for indicator creation.")
            return
        
        # RSI for 1m close
        df['rsi_1m'] = self._calculate_rsi(df['close_1m'], 14)
        # MACD for 1m
        macd, signal = self._calculate_macd(df['close_1m'])
        df['macd_1m'] = macd
        df['signal_1m'] = signal
        # Bollinger (or simpler) - just example
        df['upper_band_1m'], df['lower_band_1m'] = self._calculate_bollinger_bands(df['close_1m'])
        # EMAs
        df['ema9_1m'] = df['close_1m'].ewm(span=9, adjust=False).mean()
        df['ema21_1m'] = df['close_1m'].ewm(span=21, adjust=False).mean()
        df['ema55_1m'] = df['close_1m'].ewm(span=55, adjust=False).mean()

        # Drop partial NaNs from these calculations
        df.dropna(subset=self.indicators_1m, inplace=True)

    def create_features_for_5m(self, df):
        """
        Calculate indicators for the 5-minute columns only.
        """
        if df.empty:
            return
        needed_5m = ['open_5m', 'high_5m', 'low_5m', 'close_5m', 'volume_5m']
        if not all(c in df.columns for c in needed_5m):
            logger.warning("Missing 5m columns for indicator creation.")
            return

        df['ema9_5m'] = df['close_5m'].ewm(span=9, adjust=False).mean()
        df['ema21_5m'] = df['close_5m'].ewm(span=21, adjust=False).mean()
        df['ema55_5m'] = df['close_5m'].ewm(span=55, adjust=False).mean()
        # Simple RSI, MACD for 5m
        df['rsi_5m'] = self._calculate_rsi(df['close_5m'], 14)
        macd_5m, signal_5m = self._calculate_macd(df['close_5m'])
        df['macd_5m'] = macd_5m
        df['signal_5m'] = signal_5m

        # Drop partial NaNs from these calculations
        df.dropna(subset=self.indicators_5m, inplace=True)

    def prepare_data(self, df):
        """
        Scale the required columns, return X, y.
        We assume 'close_1m' is our target or something similar. (You can pick any column.)
        """
        try:
            if df.empty:
                return np.array([]), np.array([])

            for col in self.required_columns:
                if col not in df.columns:
                    # It's okay if 5m columns are missing if we never created them,
                    # but let's ensure we handle that logic. For simplicity,
                    # let's fill missing columns with forward fill or zero.
                    if col not in df:
                        df[col] = 0.0  # or a ffill if you prefer

            df.sort_index(ascending=True, inplace=True)
            scaled_data = self.scaler.fit_transform(df[self.required_columns])

            X, y = [], []
            # Let's pick 'close_1m' as target. If that's at index, we find it:
            if 'close_1m' in self.required_columns:
                target_idx = self.required_columns.index('close_1m')
            else:
                # fallback or raise
                target_idx = 3  # your choice

            for i in range(self.lookback, len(scaled_data) - self.prediction_window):
                X.append(scaled_data[i - self.lookback : i])
                y.append(scaled_data[i + self.prediction_window, target_idx])

            X, y = np.array(X), np.array(y)
            logger.info("Data prepared successfully", samples=X.shape[0], features=X.shape[2])
            return X, y
        except Exception as e:
            logger.error("Data preparation failed", error=str(e))
            return np.array([]), np.array([])

    # -------------------------------------------------
    # Helper methods for RSI, MACD, Bollinger, etc.
    # -------------------------------------------------
    def _calculate_rsi(self, series, period=14):
        delta = series.diff()
        gain = delta.where(delta > 0, 0.0)
        loss = -delta.where(delta < 0, 0.0)
        avg_gain = gain.rolling(period).mean()
        avg_loss = loss.rolling(period).mean()

        rs = avg_gain / (avg_loss + 1e-9)
        rsi = 100 - (100 / (1 + rs))
        return rsi

    def _calculate_macd(self, series, fastperiod=12, slowperiod=26, signalperiod=9):
        ema_fast = series.ewm(span=fastperiod, adjust=False).mean()
        ema_slow = series.ewm(span=slowperiod, adjust=False).mean()
        macd = ema_fast - ema_slow
        signal = macd.ewm(span=signalperiod, adjust=False).mean()
        return macd, signal

    def _calculate_bollinger_bands(self, series, window=20, num_std=2):
        sma = series.rolling(window).mean()
        std = series.rolling(window).std()
        upper = sma + (num_std * std)
        lower = sma - (num_std * std)
        return upper, lower
