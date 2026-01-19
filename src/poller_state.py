import asyncio


class PollerState:
    def __init__(self, enabled: bool, interval_seconds: int) -> None:
        self._interval_seconds = interval_seconds
        self._enabled_event = asyncio.Event()
        self._wake_event = asyncio.Event()
        if enabled:
            self._enabled_event.set()

    @property
    def interval_seconds(self) -> int:
        return self._interval_seconds

    def is_enabled(self) -> bool:
        return self._enabled_event.is_set()

    def set_enabled(self, enabled: bool) -> None:
        if enabled:
            self._enabled_event.set()
        else:
            self._enabled_event.clear()
        self._wake_event.set()

    def set_interval(self, interval_seconds: int) -> None:
        self._interval_seconds = interval_seconds
        self._wake_event.set()

    async def wait_until_enabled(self) -> None:
        await self._enabled_event.wait()

    async def sleep(self, delay_seconds: float) -> None:
        self._wake_event.clear()
        try:
            await asyncio.wait_for(self._wake_event.wait(), timeout=delay_seconds)
        except asyncio.TimeoutError:
            return
