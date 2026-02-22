# ledger.py
import csv
import os
import asyncio
import time
from config import TRADES_FILE

class TradeLedger:
    def __init__(self, filename):
        self.filename = filename
        self.queue = asyncio.Queue()
        
        # Initialize file with headers if it doesn't exist
        if not os.path.exists(self.filename):
            with open(self.filename, 'w', newline='') as f:
                writer = csv.writer(f)
                writer.writerow([
                    "ts", "market_id", "user_id", "outcome", 
                    "amount_shares", "price_micros", "fee_micros", "type"
                ])

    def record(self, data: dict):
        """Non-blocking record (puts data into queue)"""
        self.queue.put_nowait(data)

    async def start_worker(self):
        """Background task that writes to disk"""
        print("💾 Ledger Worker Started")
        while True:
            data = await self.queue.get()
            try:
                # Run blocking I/O in a separate thread
                await asyncio.to_thread(self._write_to_disk, data)
            except Exception as e:
                print(f"Ledger Error: {e}")
            finally:
                self.queue.task_done()

    def _write_to_disk(self, data):
        with open(self.filename, 'a', newline='') as f:
            writer = csv.writer(f)
            writer.writerow([
                data.get("ts"),
                data.get("market_id"),
                data.get("user_id"),
                data.get("outcome"),
                data.get("amount_shares"),
                data.get("price_micros"),
                data.get("fee_micros"),
                data.get("type", "TRADE")
            ])

# Global Instance
LEDGER = TradeLedger(TRADES_FILE)
