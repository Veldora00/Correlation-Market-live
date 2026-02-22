import asyncio
import os
import time

import httpx


BTC_ORACLE_URL = os.getenv(
    "BTC_ORACLE_URL",
    "https://fapi.binance.com/fapi/v1/premiumIndex?symbol=BTCUSDT",
)
ETH_ORACLE_URL = os.getenv(
    "ETH_ORACLE_URL",
    "https://fapi.binance.com/fapi/v1/premiumIndex?symbol=ETHUSDT",
)
ORACLE_TIMEOUT_SECONDS = float(os.getenv("ORACLE_TIMEOUT_SECONDS", "3"))


class Oracle:
    def __init__(self):
        self.prices = {"BTC": 0.0, "ETH": 0.0}
        self.last_update = 0.0
        self.is_healthy = False
        self.paused = False

    def is_stale(self, max_age: float = 5.0) -> bool:
        return (time.time() - self.last_update) > max_age

    async def loop(self):
        print("👁️ Oracle Loop Started")
        timeout = httpx.Timeout(ORACLE_TIMEOUT_SECONDS)
        async with httpx.AsyncClient(timeout=timeout) as client:
            while True:
                try:
                    r1, r2 = await asyncio.gather(
                        client.get(BTC_ORACLE_URL),
                        client.get(ETH_ORACLE_URL),
                    )

                    btc = float(r1.json()["markPrice"])
                    eth = float(r2.json()["markPrice"])

                    if btc < 1000 or btc > 500000:
                        raise ValueError("Bad BTC price")

                    self.prices["BTC"] = btc
                    self.prices["ETH"] = eth
                    self.last_update = time.time()
                    self.is_healthy = True
                    self.paused = False
                except Exception as e:
                    print(f"⚠️ Oracle Error: {e}")
                    self.is_healthy = False
                    self.paused = True

                await asyncio.sleep(1.0)


ORACLE_CACHE = Oracle()
