import numpy as np
from numba import njit

TOHLC = np.dtype([('DT', '<M8[us]'), ('Open', float), ('High', float), ('Low', float), ('Close', float), ('Volume', float), ('Buy', int), ('Sell', int)])


@njit
def resampleVolume(T: np.array, threshold: int, OHLC: np.array) -> int:
    t = c = 0
    volume = 0

    while t < len(T):
        open = high = low = T.PriceA[t]
        buy = sell = 0
        while t < len(T) and volume < threshold:
            volume += np.abs(T.VolumeA[t])
            if T.PriceA[t] > high:
                high = T.PriceA[t]
            if T.PriceA[t] < low:
                low = T.PriceA[t]
            t += 1
            if T.VolumeA[t] > 0:
                buy += T.VolumeA[t]
            else:
                sell += T.VolumeA[t]

        OHLC['DT'][c] = T.DateTimeA[t]
        OHLC['Open'][c] = open
        OHLC['High'][c] = high
        OHLC['Low'][c] = low
        OHLC['Close'][c] = T.PriceA[t]
        OHLC['Volume'][c] = volume
        OHLC['Buy'][c] = buy
        OHLC['Sell'][c] = sell
        c += 1
        volume = 0

    return c-1


def ohlcVolume(T: np.array, threshold: int) -> np.array:
    OHLC = np.zeros(len(T), dtype=TOHLC)
    c = resampleVolume(T, threshold, OHLC)
    OHLC.resize(c, refcheck=False)
    return OHLC