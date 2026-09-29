# Author: Daen
# CyberDeck Real-Time Audio Spectrum Visualizer Engine
# Platform: CachyOS Linux | PipeWire | CAVA

import asyncio
import logging
from typing import Set, Any

logger = logging.getLogger("cyberdeck.visualizer")

CAVA_CONFIG = """[general]
framerate = 30
bars = 32
autosens = 1
lower_cutoff_freq = 50
higher_cutoff_freq = 12000
sleep_timer = 0

[input]
method = pulse
source = Main.monitor

[output]
method = raw
raw_target = /dev/stdout
data_format = binary
bit_format = 8bit

[smoothing]
monstercat = 1
waves = 1
gravity = 100
"""


class SpectrumBroadcaster:
    """Manages an on-demand CAVA FFT audio stream and broadcasts genuine audio spectrum frames to web clients."""

    def __init__(self):
        self._subscribers: Set[Any] = set()
        self._proc: asyncio.subprocess.Process | None = None
        self._task: asyncio.Task | None = None
        self._lock = asyncio.Lock()

    async def add_subscriber(self, client):
        async with self._lock:
            self._subscribers.add(client)
            if self._proc is None:
                await self._start_cava()

    async def remove_subscriber(self, client):
        async with self._lock:
            self._subscribers.discard(client)
            if not self._subscribers and self._proc is not None:
                await self._stop_cava()

    async def _start_cava(self):
        """Start CAVA process and spawn the asynchronous frame reader loop."""
        try:
            self._proc = await asyncio.create_subprocess_exec(
                "cava", "-p", "/dev/stdin",
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.DEVNULL
            )
            self._proc.stdin.write(CAVA_CONFIG.encode("utf-8"))
            await self._proc.stdin.drain()
            self._proc.stdin.close()
            self._task = asyncio.create_task(self._reader_loop())
            logger.info(f"CAVA Audio Spectrum stream started (PID: {self._proc.pid})")
        except Exception as e:
            logger.error(f"Failed to start CAVA audio stream: {e}")
            self._proc = None

    async def _stop_cava(self):
        """Terminate CAVA process cleanly when no clients are viewing the visualizer."""
        if self._task:
            self._task.cancel()
            self._task = None

        if self._proc:
            try:
                self._proc.terminate()
                await asyncio.wait_for(self._proc.wait(), timeout=1.0)
            except Exception:
                try:
                    self._proc.kill()
                except Exception:
                    pass
            logger.info("CAVA Audio Spectrum stream stopped (no active viewers)")
            self._proc = None

    async def _reader_loop(self):
        """Read 32-band 8-bit FFT frames from CAVA and broadcast to subscribers."""
        try:
            while self._proc and self._proc.stdout:
                chunk = await self._proc.stdout.readexactly(32)
                if not chunk:
                    break

                bars = list(chunk)
                payload = {
                    "type": "spectrum",
                    "bars": bars
                }

                # Dispatch frame to all active subscribers
                dead_clients = []
                for client in list(self._subscribers):
                    try:
                        await client.send_json(payload)
                    except Exception:
                        dead_clients.append(client)

                for dead in dead_clients:
                    self._subscribers.discard(dead)

                if not self._subscribers:
                    break

        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.debug(f"CAVA reader loop error: {e}")
        finally:
            if not self._subscribers and self._proc:
                await self._stop_cava()

    async def cleanup(self):
        """Clean shutdown handler."""
        async with self._lock:
            self._subscribers.clear()
            await self._stop_cava()
