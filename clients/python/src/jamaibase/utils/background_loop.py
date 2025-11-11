# Modified from LanceDB
# https://github.com/lancedb/lancedb/blob/main/python/python/lancedb/background_loop.py

import asyncio
import threading


class BackgroundEventLoop:
    """
    A background event loop that can run futures.

    Used to bridge sync and async code, without messing with users event loops.
    """

    def __init__(self):
        self.loop = asyncio.new_event_loop()
        self.thread = threading.Thread(
            target=self.loop.run_forever,
            name="JamAIBackgroundEventLoop",
            daemon=True,
        )
        self.thread.start()

    def run(self, future):
        return asyncio.run_coroutine_threadsafe(future, self.loop).result()

    def cleanup(self):
        self.loop.call_soon_threadsafe(self.loop.stop)
        self.thread.join()
        self.loop.close()


LOOP = BackgroundEventLoop()
