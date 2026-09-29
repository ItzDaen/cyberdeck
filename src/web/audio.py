# Author: Daen
# CyberDeck Workstation & Audio System

import asyncio
import json
import logging
import re
from typing import Dict, Any, List, Optional, Callable

logger = logging.getLogger("cyberdeck.audio")

# Alias for "current hardware output" (Bluetooth when present, else HDMI/analog).
# Used by deck buttons so no hardcoded device name is needed anywhere.
HW_SINK_ALIAS = "DECK_HW"
VIRTUAL_SINKS = ("Main", "Browser", "Discord")

class AudioManager:
    def __init__(self):
        self._listeners: List[Callable[[Dict[str, Any]], None]] = []
        self._subscribe_task: Optional[asyncio.Task] = None
        self._last_state: Dict[str, Any] = {"sources": {}, "sinks": {}, "discord": {}}
        self._lock = asyncio.Lock()

    def register_listener(self, callback: Callable[[Dict[str, Any]], None]):
        self._listeners.append(callback)

    def unregister_listener(self, callback: Callable[[Dict[str, Any]], None]):
        if callback in self._listeners:
            self._listeners.remove(callback)

    async def get_state(self) -> Dict[str, Any]:
        """Fetch current audio state asynchronously using pactl json output."""
        async with self._lock:
            sources_dict = {}
            sinks_dict = {}

            # Fetch sources
            try:
                proc = await asyncio.create_subprocess_exec(
                    "pactl", "-f", "json", "list", "sources",
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )
                stdout, _ = await proc.communicate()
                if proc.returncode == 0 and stdout:
                    sources_data = json.loads(stdout.decode("utf-8"))
                    for src in sources_data:
                        name = src.get("name", "")
                        if not name:
                            continue
                        
                        vol_percent = 100
                        vol_dict = src.get("volume", {})
                        if isinstance(vol_dict, dict):
                            for ch_name, ch_data in vol_dict.items():
                                if isinstance(ch_data, dict) and "value_percent" in ch_data:
                                    pct_str = ch_data["value_percent"].replace("%", "").strip()
                                    try:
                                        vol_percent = int(pct_str)
                                        break
                                    except ValueError:
                                        pass

                        is_monitor = name.endswith(".monitor") or "monitor" in src.get("flags", [])
                        sources_dict[name] = {
                            "name": name,
                            "description": src.get("description", name),
                            "mute": bool(src.get("mute", False)),
                            "volume": vol_percent,
                            "is_monitor": is_monitor,
                            "state": src.get("state", "IDLE")
                        }
            except Exception as e:
                logger.error(f"Error fetching sources: {e}")

            # Fetch sinks
            try:
                proc = await asyncio.create_subprocess_exec(
                    "pactl", "-f", "json", "list", "sinks",
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )
                stdout, _ = await proc.communicate()
                if proc.returncode == 0 and stdout:
                    sinks_data = json.loads(stdout.decode("utf-8"))
                    for sink in sinks_data:
                        name = sink.get("name", "")
                        if not name:
                            continue
                        
                        vol_percent = 100
                        vol_dict = sink.get("volume", {})
                        if isinstance(vol_dict, dict):
                            for ch_name, ch_data in vol_dict.items():
                                if isinstance(ch_data, dict) and "value_percent" in ch_data:
                                    pct_str = ch_data["value_percent"].replace("%", "").strip()
                                    try:
                                        vol_percent = int(pct_str)
                                        break
                                    except ValueError:
                                        pass

                        sinks_dict[name] = {
                            "name": name,
                            "description": sink.get("description", name),
                            "mute": bool(sink.get("mute", False)),
                            "volume": vol_percent,
                            "state": sink.get("state", "IDLE")
                        }
            except Exception as e:
                logger.error(f"Error fetching sinks: {e}")

            # Fetch Discord State
            discord_state = {"mic_muted": False, "audio_muted": False, "active": False}
            try:
                # Check Discord Input Stream
                src_out_proc = await asyncio.create_subprocess_exec(
                    "pactl", "-f", "json", "list", "source-outputs",
                    stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
                )
                so_stdout, _ = await src_out_proc.communicate()
                if src_out_proc.returncode == 0 and so_stdout:
                    so_data = json.loads(so_stdout.decode("utf-8"))
                    discord_inputs = [
                        s for s in so_data
                        if s.get("properties", {}).get("application.process.binary") == "Discord"
                        or "discord" in s.get("properties", {}).get("application.name", "").lower()
                    ]
                    if discord_inputs:
                        discord_state["active"] = True
                        discord_state["mic_muted"] = all(s.get("mute", False) for s in discord_inputs)

                # Check Discord Output Sink
                if "Discord" in sinks_dict:
                    discord_state["audio_muted"] = sinks_dict["Discord"]["mute"]
            except Exception as e:
                logger.debug(f"Error checking Discord state: {e}")

            self._last_state = {
                "sources": sources_dict,
                "sinks": sinks_dict,
                "discord": discord_state
            }
            return self._last_state

    async def toggle_source_mute(self, source_name: str) -> bool:
        if not self._is_valid_name(source_name):
            raise ValueError("Invalid source name")
        proc = await asyncio.create_subprocess_exec(
            "pactl", "set-source-mute", source_name, "toggle",
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )
        await proc.communicate()
        return proc.returncode == 0

    async def set_source_mute(self, source_name: str, mute: bool) -> bool:
        if not self._is_valid_name(source_name):
            raise ValueError("Invalid source name")
        val = "1" if mute else "0"
        proc = await asyncio.create_subprocess_exec(
            "pactl", "set-source-mute", source_name, val,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )
        await proc.communicate()
        return proc.returncode == 0

    async def set_source_volume(self, source_name: str, percent: int) -> bool:
        if not self._is_valid_name(source_name):
            raise ValueError("Invalid source name")
        percent = max(0, min(150, int(percent)))
        proc = await asyncio.create_subprocess_exec(
            "pactl", "set-source-volume", source_name, f"{percent}%",
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )
        await proc.communicate()
        return proc.returncode == 0

    async def toggle_sink_mute(self, sink_name: str) -> bool:
        if not self._is_valid_name(sink_name):
            raise ValueError("Invalid sink name")
        if sink_name == HW_SINK_ALIAS:
            sink_name = await self.resolve_hw_sink()
            if not sink_name:
                return False
        proc = await asyncio.create_subprocess_exec(
            "pactl", "set-sink-mute", sink_name, "toggle",
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )
        await proc.communicate()
        return proc.returncode == 0

    async def set_sink_mute(self, sink_name: str, mute: bool) -> bool:
        if not self._is_valid_name(sink_name):
            raise ValueError("Invalid sink name")
        if sink_name == HW_SINK_ALIAS:
            sink_name = await self.resolve_hw_sink()
            if not sink_name:
                return False
        val = "1" if mute else "0"
        proc = await asyncio.create_subprocess_exec(
            "pactl", "set-sink-mute", sink_name, val,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )
        await proc.communicate()
        return proc.returncode == 0

    async def set_sink_volume(self, sink_name: str, percent: int) -> bool:
        if not self._is_valid_name(sink_name):
            raise ValueError("Invalid sink name")
        if sink_name == HW_SINK_ALIAS:
            sink_name = await self.resolve_hw_sink()
            if not sink_name:
                return False
        percent = max(0, min(150, int(percent)))
        proc = await asyncio.create_subprocess_exec(
            "pactl", "set-sink-volume", sink_name, f"{percent}%",
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )
        await proc.communicate()
        return proc.returncode == 0

    async def mute_all_mics(self, mute: Optional[bool] = None) -> bool:
        """Mute or toggle all capture microphone sources."""
        state = await self.get_state()
        sources = state.get("sources", {})
        mics = [s for s in sources.values() if not s["is_monitor"]]
        
        if mute is None:
            any_unmuted = any(not m["mute"] for m in mics)
            target_mute = any_unmuted
        else:
            target_mute = mute

        tasks = []
        for m in mics:
            tasks.append(self.set_source_mute(m["name"], target_mute))
        if tasks:
            await asyncio.gather(*tasks)
        return target_mute

    async def toggle_discord_mic_mute(self) -> bool:
        """Toggle mute specifically on Discord's voice recording input stream."""
        try:
            proc = await asyncio.create_subprocess_exec(
                "pactl", "-f", "json", "list", "source-outputs",
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
            )
            stdout, _ = await proc.communicate()
            if proc.returncode == 0 and stdout:
                data = json.loads(stdout.decode("utf-8"))
                discord_streams = [
                    s for s in data
                    if s.get("properties", {}).get("application.process.binary") == "Discord"
                    or "discord" in s.get("properties", {}).get("application.name", "").lower()
                ]
                if discord_streams:
                    for s in discord_streams:
                        idx = str(s["index"])
                        p = await asyncio.create_subprocess_exec(
                            "pactl", "set-source-output-mute", idx, "toggle"
                        )
                        await p.communicate()
                    return True
        except Exception as e:
            logger.error(f"Error toggling Discord mic: {e}")
        return False

    async def toggle_discord_audio_mute(self) -> bool:
        """Toggle mute on Discord audio playback (Deafen)."""
        return await self.toggle_sink_mute("Discord")

    def _is_valid_name(self, name: str) -> bool:
        return bool(re.match(r"^[a-zA-Z0-9_\-\.:@]+$", name))

    async def resolve_hw_sink(self) -> str:
        """Return current hardware sink name (never a virtual deck sink).
        Priority: running Bluetooth > running ALSA > any Bluetooth > any ALSA.
        Empty string when no hardware sink exists."""
        try:
            proc = await asyncio.create_subprocess_exec(
                "pactl", "list", "sinks", "short",
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
            )
            stdout, _ = await proc.communicate()
            if proc.returncode != 0 or not stdout:
                return ""
        except Exception:
            return ""
        cands = []
        for line in stdout.decode("utf-8", errors="ignore").splitlines():
            parts = line.split()
            if len(parts) < 2:
                continue
            name, state = parts[1], parts[-1] if len(parts) > 2 else ""
            base = name.split(":")[0] if ":" in name else name
            if base in VIRTUAL_SINKS or "easyeffects" in name or "gsr" in name:
                continue
            if name.startswith("bluez_output"):
                score = 50 if state == "RUNNING" else 30
            elif name.startswith("alsa_output"):
                score = 40 if state == "RUNNING" else 20
            else:
                continue
            cands.append((score, name))
        if not cands:
            return ""
        cands.sort(reverse=True)
        return cands[0][1]

    async def start_event_subscriber(self):
        while True:
            try:
                proc = await asyncio.create_subprocess_exec(
                    "pactl", "subscribe",
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )
                while True:
                    line = await proc.stdout.readline()
                    if not line:
                        break
                    decoded = line.decode("utf-8", errors="ignore").strip()
                    if "source" in decoded or "sink" in decoded or "server" in decoded:
                        await asyncio.sleep(0.04)
                        new_state = await self.get_state()
                        for listener in list(self._listeners):
                            try:
                                if asyncio.iscoroutinefunction(listener):
                                    asyncio.create_task(listener(new_state))
                                else:
                                    listener(new_state)
                            except Exception as e:
                                logger.error(f"Error calling audio listener: {e}")
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"pactl subscribe error: {e}")
                await asyncio.sleep(2)
