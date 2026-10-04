#!/usr/bin/env python3
# Author: Daen
# Deck Audio Router v2.0 (ex CyberCAVA router)
# Two jobs, one daemon:
#  1. CAVA: route all virtual deck monitors (Main, Browser, Discord) into any
#     running CAVA instance, never microphones (MicGuard).
#  2. HARDWARE: link the virtual channel outputs (*_Stream) to the current
#     hardware sink (Bluetooth when present, else HDMI/analog) and re-link
#     automatically on connect/disconnect. No hardcoded device, no restarts.
# Does not alter recording tracks or default device settings.

import asyncio
import logging
import os
import re
import signal
import subprocess
import time

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger("deck-audio-router")

TARGET_SINKS = ("Main", "Browser", "Discord")
FALLBACK_SINKS = ("bluez_output", "alsa_output")
STREAM_NODES = ("Discord_Stream", "Browser_Stream", "Main_Stream")
VIRTUAL_SINKS = set(TARGET_SINKS)
HW_STATE_FILE = os.path.expanduser("~/.cache/deck_hw_target")
HW_OVERRIDE_FILE = os.path.expanduser("~/.config/deck/audio-target")

class CavaAudioRouter:
    def __init__(self):
        self._running = True
        self._last_sync = 0
        self._sync_lock = asyncio.Lock()

    def sync_links(self) -> int:
        """Scan PipeWire ports and links, connecting all target monitor channels to cava inputs.
        Microphones are never linked: only *.monitor ports are eligible. Any existing
        mic->cava link is actively removed."""
        try:
            res_o = subprocess.run(["pw-link", "-I", "-o"], capture_output=True, text=True, timeout=2.0)
            res_i = subprocess.run(["pw-link", "-I", "-i"], capture_output=True, text=True, timeout=2.0)
            res_l = subprocess.run(["pw-link", "-I", "-l"], capture_output=True, text=True, timeout=2.0)
            if res_o.returncode != 0 or res_i.returncode != 0:
                return 0
        except Exception as e:
            logger.debug(f"Error running pw-link: {e}")
            return 0

        # Map port id -> port name for mic-link detection
        port_names = {}
        for line in (res_o.stdout.splitlines() + res_i.stdout.splitlines()):
            m = re.match(r"^\s*(\d+)\s+([^\s]+)$", line)
            if m:
                port_names[int(m.group(1))] = m.group(2)

        # 1. Parse all available output monitors (even those with 0 active links)
        monitors_fl = []
        monitors_fr = []
        fallback_fl = []
        fallback_fr = []

        for line in res_o.stdout.splitlines():
            m = re.match(r"^\s*(\d+)\s+([^\s]+)$", line)
            if not m:
                continue
            pid, pname = int(m.group(1)), m.group(2)

            for sink in TARGET_SINKS:
                if pname == f"{sink}:monitor_FL":
                    monitors_fl.append(pid)
                elif pname == f"{sink}:monitor_FR":
                    monitors_fr.append(pid)

            for fb in FALLBACK_SINKS:
                if fb in pname and "cava" not in pname and "gsr" not in pname:
                    if "monitor_FL" in pname:
                        fallback_fl.append(pid)
                    elif "monitor_FR" in pname:
                        fallback_fr.append(pid)

        # 2. Parse all CAVA input capture ports
        cava_inputs_fl = []
        cava_inputs_fr = []
        for line in res_i.stdout.splitlines():
            m = re.match(r"^\s*(\d+)\s+([^\s]+)$", line)
            if not m:
                continue
            pid, pname = int(m.group(1)), m.group(2)
            if "cava:input_FL" in pname:
                cava_inputs_fl.append(pid)
            elif "cava:input_FR" in pname:
                cava_inputs_fr.append(pid)

        if not cava_inputs_fl and not cava_inputs_fr:
            return 0

        # 3. Parse currently established links
        current_links = set()
        current_out_id = None
        for line in res_l.stdout.splitlines():
            m_port = re.match(r"^\s*(\d+)\s+[^\s]+$", line)
            if m_port:
                current_out_id = int(m_port.group(1))
                continue
            m_link = re.match(r"^\s*\d+\s+\|->\s+(\d+)", line)
            if m_link and current_out_id is not None:
                current_links.add((current_out_id, int(m_link.group(1))))

        active_fl = monitors_fl if monitors_fl else fallback_fl
        active_fr = monitors_fr if monitors_fr else fallback_fr

        # 4. Actively disconnect any mic->cava link (non-monitor source feeding cava)
        cava_ids = set(cava_inputs_fl) | set(cava_inputs_fr)
        for (out_id, in_id) in list(current_links):
            if in_id in cava_ids:
                out_name = port_names.get(out_id, "")
                if "cava:input" not in out_name and ":monitor_" not in out_name and "monitor_FL" not in out_name and "monitor_FR" not in out_name:
                    subprocess.run(["pw-link", "-d", str(out_id), str(in_id)], capture_output=True, timeout=5.0)
                    logger.info(f"[MicGuard] Disconnected mic source {out_name} from CAVA.")
                    current_links.discard((out_id, in_id))

        # 5. Virtual_Mic silence invariant: virtual_mic_capture must stay UNLINKED.
        #    Its unlinked capture yields digital silence by design (Resolve init
        #    placeholder). Anything linked into it (EE output, mics, monitors)
        #    is removed, whoever created it.
        for (out_id, in_id) in list(current_links):
            in_name = port_names.get(in_id, "")
            if in_name.startswith("virtual_mic_capture:input_"):
                out_name = port_names.get(out_id, "")
                subprocess.run(["pw-link", "-d", str(out_id), str(in_id)], capture_output=True, timeout=5.0)
                logger.warning(f"[VmicGuard] Removed link {out_name} -> {in_name} (Virtual_Mic must stay silent).")
                current_links.discard((out_id, in_id))

        created = 0
        # Connect FL monitors to FL cava inputs
        for mon_id in active_fl:
            for cava_id in cava_inputs_fl:
                if (mon_id, cava_id) not in current_links:
                    p = subprocess.run(["pw-link", str(mon_id), str(cava_id)], capture_output=True, timeout=5.0)
                    if p.returncode == 0:
                        created += 1

        # Connect FR monitors to FR cava inputs
        for mon_id in active_fr:
            for cava_id in cava_inputs_fr:
                if (mon_id, cava_id) not in current_links:
                    p = subprocess.run(["pw-link", str(mon_id), str(cava_id)], capture_output=True, timeout=5.0)
                    if p.returncode == 0:
                        created += 1

        return created

    def _read_hw_override(self) -> str:
        try:
            with open(HW_OVERRIDE_FILE, "r", encoding="utf-8") as f:
                val = f.read().strip()
                return val
        except Exception:
            return ""

    def _discover_hw_sink(self) -> str:
        """Pick current hardware sink: override pin > running BT > running alsa >
        suspended BT > suspended alsa. Never a virtual deck sink."""
        override = self._read_hw_override()
        try:
            res = subprocess.run(["pactl", "list", "sinks", "short"],
                                 capture_output=True, text=True, timeout=3.0)
            if res.returncode != 0:
                return ""
        except Exception:
            return ""
        cands = []  # (score, name)
        for line in res.stdout.splitlines():
            parts = line.split()
            if len(parts) < 2:
                continue
            name, state = parts[1], parts[-1] if len(parts) > 2 else ""
            base = name.split(":")[0] if ":" in name else name
            if base in VIRTUAL_SINKS or "easyeffects" in name or "gsr" in name:
                continue
            if not (name.startswith("bluez_output") or name.startswith("alsa_output")):
                continue
            score = 0
            if override and (name == override or name.startswith(override)):
                score = 100
            elif name.startswith("bluez_output"):
                score = 60 if state == "RUNNING" else 45
            elif name.startswith("alsa_output"):
                score = 40 if state == "RUNNING" else 15
            if state == "SUSPENDED":
                score -= 5
            cands.append((score, name))
        if not cands:
            return ""
        cands.sort(reverse=True)
        return cands[0][1]

    def _read_last_hw(self) -> str:
        try:
            with open(HW_STATE_FILE, "r", encoding="utf-8") as f:
                return f.read().strip()
        except Exception:
            return ""

    def _write_last_hw(self, name: str):
        try:
            os.makedirs(os.path.dirname(HW_STATE_FILE), exist_ok=True)
            with open(HW_STATE_FILE, "w", encoding="utf-8") as f:
                f.write(name)
        except Exception:
            pass

    def sync_hw_links(self) -> int:
        """Link *_Stream outputs to the current hardware sink playback ports.
        Unlinks stale hardware targets so audio never doubles on two outputs."""
        hw = self._discover_hw_sink()
        if not hw:
            return 0
        try:
            res_o = subprocess.run(["pw-link", "-I", "-o"], capture_output=True, text=True, timeout=2.0)
            res_i = subprocess.run(["pw-link", "-I", "-i"], capture_output=True, text=True, timeout=2.0)
            res_l = subprocess.run(["pw-link", "-I", "-l"], capture_output=True, text=True, timeout=2.0)
            if res_o.returncode != 0 or res_i.returncode != 0:
                return 0
        except Exception as e:
            logger.debug(f"Error running pw-link for hw sync: {e}")
            return 0

        out_ports = {}  # name -> id (stream output ports live here)
        for line in res_o.stdout.splitlines():
            m = re.match(r"^\s*(\d+)\s+([^\s]+)$", line)
            if m:
                out_ports[m.group(2)] = int(m.group(1))

        in_ports = {}  # name -> id (hardware playback ports live here)
        for line in res_i.stdout.splitlines():
            m = re.match(r"^\s*(\d+)\s+([^\s]+)$", line)
            if m:
                in_ports[m.group(2)] = int(m.group(1))

        hw_fl = in_ports.get(f"{hw}:playback_FL")
        hw_fr = in_ports.get(f"{hw}:playback_FR")
        if hw_fl is None or hw_fr is None:
            return 0

        # Parse existing links: out_id -> set(in_ids), with names
        id_to_name = {v: k for k, v in out_ports.items()}
        id_to_name.update({v: k for k, v in in_ports.items()})

        links = {}  # out_id -> set(in_id)
        cur_out = None
        for line in res_l.stdout.splitlines():
            m_port = re.match(r"^\s*(\d+)\s+[^\s]+$", line)
            if m_port:
                cur_out = int(m_port.group(1))
                continue
            m_link = re.match(r"^\s*\d+\s+\|->\s+(\d+)", line)
            if m_link and cur_out is not None:
                links.setdefault(cur_out, set()).add(int(m_link.group(1)))

        changed = 0
        last_hw = self._read_last_hw()
        if hw != last_hw:
            logger.info(f"[HW] Hardware target: {last_hw or 'none'} -> {hw}")
            self._write_last_hw(hw)

        for stream in STREAM_NODES:
            for ch, hw_port in (("FL", hw_fl), ("FR", hw_fr)):
                sport = out_ports.get(f"{stream}:output_{ch}")
                if sport is None:
                    continue
                linked = links.get(sport, set())
                # Remove links to wrong hardware inputs
                for in_id in list(linked):
                    in_name = id_to_name.get(in_id, "")
                    if in_name in (f"{hw}:playback_FL", f"{hw}:playback_FR"):
                        continue
                    if ":playback_" in in_name:
                        p = subprocess.run(["pw-link", "-d", str(sport), str(in_id)],
                                           capture_output=True, timeout=5.0)
                        if p.returncode == 0:
                            changed += 1
                            logger.info(f"[HW] Unlinked stale {stream}:output_{ch} -> {in_name}")
                # Ensure link to current hardware
                if hw_port not in links.get(sport, set()):
                    p = subprocess.run(["pw-link", str(sport), str(hw_port)], capture_output=True, timeout=5.0)
                    if p.returncode == 0:
                        changed += 1
        return changed

    async def run(self):
        logger.info("Deck Audio Router v2.0 starting up...")

        # Initial sync
        initial_created = self.sync_links()
        if initial_created > 0:
            logger.info(f"Initial sync: connected {initial_created} audio routes into CAVA.")
        else:
            logger.info("Initial sync: all CAVA audio routes already connected or idle.")
        hw_created = self.sync_hw_links()
        if hw_created > 0:
            logger.info(f"Initial sync: connected {hw_created} hardware output routes.")
        else:
            logger.info("Initial sync: hardware output routes already connected.")

        # Start pw-mon event loop
        proc = None
        try:
            proc = await asyncio.create_subprocess_exec(
                "pw-mon", "-N",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.DEVNULL
            )
        except Exception as e:
            logger.error(f"Failed to start pw-mon: {e}")

        # Heartbeat task (periodic fallback check)
        async def heartbeat():
            slow = 0
            while self._running:
                await asyncio.sleep(2.0)
                try:
                    c = self.sync_links()
                    if c > 0:
                        logger.info(f"[Heartbeat] Connected {c} missing CAVA routes.")
                    slow += 1
                    if slow >= 3:
                        slow = 0
                        h = self.sync_hw_links()
                        if h > 0:
                            logger.info(f"[Heartbeat] Fixed {h} hardware output routes.")
                except Exception as e:
                    logger.debug(f"Heartbeat error: {e}")

        heartbeat_task = asyncio.create_task(heartbeat())

        # Event stream reader
        keywords = ("cava", "Main", "Browser", "Discord", "_Stream", "bluez_output", "alsa_output", "PipeWire:Interface:Port", "PipeWire:Interface:Node", "PipeWire:Interface:Link")
        while self._running and proc and proc.stdout:
            try:
                line = await proc.stdout.readline()
                if not line:
                    break
                text = line.decode("utf-8", errors="ignore")
                if any(k in text for k in keywords):
                    now = time.time()
                    if now - self._last_sync > 0.15:
                        self._last_sync = now
                        await asyncio.sleep(0.1)  # Brief settle time for WirePlumber default link
                        c = self.sync_links()
                        if c > 0:
                            logger.info(f"[Event] Connected {c} new audio routes into CAVA.")
                        h = self.sync_hw_links()
                        if h > 0:
                            logger.info(f"[Event] Fixed {h} hardware output routes.")
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.debug(f"Event loop exception: {e}")
                await asyncio.sleep(0.5)

        heartbeat_task.cancel()
        if proc:
            try:
                proc.terminate()
            except Exception:
                pass

    def stop(self):
        self._running = False

async def async_main():
    router = CavaAudioRouter()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, router.stop)
    await router.run()

def main():
    try:
        asyncio.run(async_main())
    except (KeyboardInterrupt, SystemExit):
        pass

if __name__ == "__main__":
    main()
