# Author: Daen
# CyberDeck Telemetry Engine - Comprehensive Hardware Diagnostics
# Platform: CachyOS Linux | AMD Ryzen | AMD Radeon RX 6600 XT | Nuvoton NCT6797

import asyncio
import glob
import os
import time
from typing import Dict, Any, Optional, List

import psutil


class TelemetryManager:
    """Comprehensive hardware telemetry engine reading every active workstation sensor."""

    def __init__(self):
        self._hwmons: Dict[str, str] = {}
        self._nvme_hwmons: List[str] = []
        self._gpu_device_dir: Optional[str] = None
        self._last_net_io = None
        self._last_net_time = 0.0
        self._last_disk_io = None
        self._last_disk_time = 0.0
        self._boot_time = psutil.boot_time()
        self._cached_power_profile = "balanced"
        self._last_profile_check = 0.0

        # Discover sensors dynamically
        self._discover_hardware()

    def _discover_hardware(self):
        """Locate sysfs and hwmon paths dynamically."""
        self._hwmons.clear()
        self._nvme_hwmons.clear()

        for hw in sorted(glob.glob("/sys/class/hwmon/hwmon*")):
            name_file = os.path.join(hw, "name")
            if os.path.exists(name_file):
                try:
                    with open(name_file, "r", encoding="utf-8") as f:
                        name = f.read().strip()
                        self._hwmons[name] = hw
                        if name == "nvme":
                            self._nvme_hwmons.append(hw)
                except Exception:
                    pass

        # Locate AMD GPU device sysfs directory
        for card in glob.glob("/sys/class/drm/card[0-9]*/device"):
            if os.path.exists(os.path.join(card, "gpu_busy_percent")):
                self._gpu_device_dir = card
                break

    def _read_int(self, filepath: str) -> Optional[int]:
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                return int(f.read().strip())
        except Exception:
            return None

    def _read_temp_c(self, hw_name: str, filename: str) -> Optional[float]:
        """Read temperature in Celsius from hwmon, filtering invalid or zero readings."""
        if hw_name in self._hwmons:
            p = os.path.join(self._hwmons[hw_name], filename)
            val = self._read_int(p)
            if val is not None:
                deg = round(val / 1000.0, 1)
                # Filter out unpopulated sensor sentinel values (e.g. -128°C or 0.0°C fixed)
                if 5.0 <= deg <= 125.0:
                    return deg
        return None

    async def get_active_power_profile(self) -> str:
        """Fetch active power profile via powerprofilesctl with caching."""
        now = time.time()
        if now - self._last_profile_check < 3.0:
            return self._cached_power_profile

        self._last_profile_check = now
        try:
            proc = await asyncio.create_subprocess_exec(
                "powerprofilesctl", "get",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, _ = await proc.communicate()
            if proc.returncode == 0 and stdout:
                self._cached_power_profile = stdout.decode("utf-8").strip()
        except Exception:
            pass
        return self._cached_power_profile

    def _get_cpu_governor(self) -> str:
        try:
            with open("/sys/devices/system/cpu/cpu0/cpufreq/scaling_governor", "r", encoding="utf-8") as f:
                return f.read().strip()
        except Exception:
            return "unknown"

    async def get_telemetry(self) -> Dict[str, Any]:
        """Collect exhaustive workstation hardware sensor snapshot."""
        now = time.time()

        if not self._gpu_device_dir or not self._hwmons:
            self._discover_hardware()

        # ---------------------------------------------------------
        # 1. CPU Metrics (AMD Ryzen 7 3800X)
        # ---------------------------------------------------------
        cpu_percent = psutil.cpu_percent(interval=None)
        cpu_per_core = psutil.cpu_percent(interval=None, percpu=True)
        cpu_freq = psutil.cpu_freq()
        load_avg = os.getloadavg()
        cpu_governor = self._get_cpu_governor()

        # Detailed per-thread metrics (load, current freq, physical core mapping)
        cores_detail = []
        for i, core_pct in enumerate(cpu_per_core):
            f_khz = 0
            try:
                with open(f"/sys/devices/system/cpu/cpu{i}/cpufreq/scaling_cur_freq", "r") as ff:
                    f_khz = int(ff.read().strip())
            except Exception:
                pass

            phys_core = i % 8
            try:
                with open(f"/sys/devices/system/cpu/cpu{i}/topology/core_id", "r") as tf:
                    phys_core = int(tf.read().strip())
            except Exception:
                pass

            cores_detail.append({
                "thread": i + 1,
                "core": phys_core,
                "load": round(core_pct, 1),
                "freq_mhz": round(f_khz / 1000.0) if f_khz else (round(cpu_freq.current) if cpu_freq else 0)
            })

        # CPU package (Tctl) and CCD1 die temperatures
        cpu_tctl = self._read_temp_c("k10temp", "temp1_input")
        cpu_tccd1 = self._read_temp_c("k10temp", "temp3_input")

        # ---------------------------------------------------------
        # 2. Motherboard Temperatures & Calibrated Voltages (MSI B450 / NCT6797)
        # ---------------------------------------------------------
        mb_socket = self._read_temp_c("nct6797", "temp2_input")   # CPUTIN
        mb_system = self._read_temp_c("nct6797", "temp1_input")   # SYSTIN
        mb_vrm = self._read_temp_c("nct6797", "temp3_input")      # AUXTIN0 (VRM)
        mb_chipset = self._read_temp_c("nct6797", "temp5_input")  # AUXTIN2 (Chipset)
        mb_smbus = self._read_temp_c("nct6797", "temp7_input")    # SMBUSMASTER 0
        mb_tsi0 = self._read_temp_c("nct6797", "temp13_input")    # TSI0_TEMP

        # Calibrated Essential Voltages (MSI B450 GAMING PLUS MAX specification)
        mb_voltages = {}
        if "nct6797" in self._hwmons:
            base = self._hwmons["nct6797"]
            raw_in0 = self._read_int(os.path.join(base, "in0_input"))    # CPU Vcore
            raw_in1 = self._read_int(os.path.join(base, "in1_input"))    # ATX +5V (resistor scale 5.0x)
            raw_in3 = self._read_int(os.path.join(base, "in3_input"))    # ATX +3.3V
            raw_in4 = self._read_int(os.path.join(base, "in4_input"))    # ATX +12V (resistor scale 12.0x)
            raw_in8 = self._read_int(os.path.join(base, "in8_input"))    # CMOS Battery (CR2032 RTC)
            raw_in9 = self._read_int(os.path.join(base, "in9_input"))    # CPU 1.8V PLL
            raw_in12 = self._read_int(os.path.join(base, "in12_input"))  # CPU Vsoc (AMD SoC / IF)
            raw_in13 = self._read_int(os.path.join(base, "in13_input"))  # DRAM Voltage (resistor scale 2.0x)

            if raw_in0 and raw_in0 > 0:
                mb_voltages["cpu_vcore"] = round(raw_in0 / 1000.0, 3)
            if raw_in12 and raw_in12 > 0:
                mb_voltages["cpu_vsoc"] = round(raw_in12 / 1000.0, 3)
            if raw_in13 and raw_in13 > 0:
                mb_voltages["dram"] = round((raw_in13 / 1000.0) * 2.0, 3)
            if raw_in4 and raw_in4 > 0:
                mb_voltages["atx_12v"] = round((raw_in4 / 1000.0) * 12.0, 2)
            if raw_in1 and raw_in1 > 0:
                mb_voltages["atx_5v"] = round((raw_in1 / 1000.0) * 5.0, 2)
            if raw_in3 and raw_in3 > 0:
                mb_voltages["atx_3v3"] = round(raw_in3 / 1000.0, 2)
            if raw_in9 and raw_in9 > 0:
                mb_voltages["cpu_pll_1v8"] = round(raw_in9 / 1000.0, 2)
            if raw_in8 and raw_in8 > 0:
                mb_voltages["cmos_battery"] = round(raw_in8 / 1000.0, 2)

        # ---------------------------------------------------------
        # 3. Active Cooling Fans (Filter out disconnected/0 RPM headers)
        # ---------------------------------------------------------
        fans = {}
        if "nct6797" in self._hwmons:
            base = self._hwmons["nct6797"]
            fan_labels = [
                ("cpu_cooler", "fan2_input"),
                ("chassis_fan_1", "fan5_input"),
                ("chassis_fan_2", "fan6_input")
            ]
            for label, f_name in fan_labels:
                rpm = self._read_int(os.path.join(base, f_name))
                if rpm and rpm > 0:
                    fans[label] = rpm

        # ---------------------------------------------------------
        # 4. Storage NVMe SSDs & WiFi Temperatures
        # ---------------------------------------------------------
        storage_temps = {}
        for idx, hw in enumerate(self._nvme_hwmons):
            comp = self._read_int(os.path.join(hw, "temp1_input"))
            s1 = self._read_int(os.path.join(hw, "temp2_input"))
            s2 = self._read_int(os.path.join(hw, "temp3_input"))
            
            drive_data = {}
            if comp is not None and comp > 0:
                drive_data["composite_c"] = round(comp / 1000.0, 1)
            if s1 is not None and s1 > 0:
                drive_data["sensor_1_c"] = round(s1 / 1000.0, 1)
            if s2 is not None and s2 > 0:
                drive_data["sensor_2_c"] = round(s2 / 1000.0, 1)
            
            if drive_data:
                storage_temps[f"nvme_{idx + 1}"] = drive_data

        wifi_temp = self._read_temp_c("iwlwifi_1", "temp1_input")

        # ---------------------------------------------------------
        # 5. GPU AMD Radeon RX 6600 XT
        # ---------------------------------------------------------
        gpu = {
            "busy_percent": 0,
            "vram_used_mb": 0,
            "vram_total_mb": 8176,
            "vram_percent": 0.0,
            "temp_edge": 0.0,
            "temp_hotspot": 0.0,
            "temp_mem": 0.0,
            "power_watts": 0.0,
            "fan_rpm": 0,
            "sclk_mhz": 0,
            "mclk_mhz": 0,
            "vddgfx_mv": 0
        }

        if self._gpu_device_dir:
            busy = self._read_int(os.path.join(self._gpu_device_dir, "gpu_busy_percent"))
            if busy is not None:
                gpu["busy_percent"] = busy

            vram_used = self._read_int(os.path.join(self._gpu_device_dir, "mem_info_vram_used"))
            vram_total = self._read_int(os.path.join(self._gpu_device_dir, "mem_info_vram_total"))
            if vram_used is not None and vram_total:
                gpu["vram_used_mb"] = round(vram_used / (1024 * 1024))
                gpu["vram_total_mb"] = round(vram_total / (1024 * 1024))
                gpu["vram_percent"] = round((vram_used / vram_total) * 100, 1)

        if "amdgpu" in self._hwmons:
            base = self._hwmons["amdgpu"]
            t_edge = self._read_int(os.path.join(base, "temp1_input"))
            t_hot = self._read_int(os.path.join(base, "temp2_input"))
            t_mem = self._read_int(os.path.join(base, "temp3_input"))
            pwr = self._read_int(os.path.join(base, "power1_average"))
            fan = self._read_int(os.path.join(base, "fan1_input"))
            f1 = self._read_int(os.path.join(base, "freq1_input"))
            f2 = self._read_int(os.path.join(base, "freq2_input"))
            vdd = self._read_int(os.path.join(base, "in0_input"))

            if t_edge is not None:
                gpu["temp_edge"] = round(t_edge / 1000.0, 1)
            if t_hot is not None:
                gpu["temp_hotspot"] = round(t_hot / 1000.0, 1)
            if t_mem is not None:
                gpu["temp_mem"] = round(t_mem / 1000.0, 1)
            if pwr is not None:
                gpu["power_watts"] = round(pwr / 1000000.0, 1)
            if fan is not None:
                gpu["fan_rpm"] = fan
            if f1 is not None:
                gpu["sclk_mhz"] = round(f1 / 1000000.0)
            if f2 is not None:
                gpu["mclk_mhz"] = round(f2 / 1000000.0)
            if vdd is not None:
                gpu["vddgfx_mv"] = vdd

        # ---------------------------------------------------------
        # 6. RAM & Swap Memory
        # ---------------------------------------------------------
        vmem = psutil.virtual_memory()
        swap = psutil.swap_memory()

        # ---------------------------------------------------------
        # 7. Disks & Throughput
        # ---------------------------------------------------------
        disk_root = psutil.disk_usage("/")
        disk_io = psutil.disk_io_counters()
        disk_read_rate = 0
        disk_write_rate = 0
        if disk_io and self._last_disk_io and self._last_disk_time > 0:
            dt = max(0.1, now - self._last_disk_time)
            disk_read_rate = round((disk_io.read_bytes - self._last_disk_io.read_bytes) / dt)
            disk_write_rate = round((disk_io.write_bytes - self._last_disk_io.write_bytes) / dt)
        self._last_disk_io = disk_io
        self._last_disk_time = now

        # Network Throughput
        net_io = psutil.net_io_counters()
        net_rx_rate = 0
        net_tx_rate = 0
        if self._last_net_io and self._last_net_time > 0:
            dt = max(0.1, now - self._last_net_time)
            net_rx_rate = round((net_io.bytes_recv - self._last_net_io.bytes_recv) / dt)
            net_tx_rate = round((net_io.bytes_sent - self._last_net_io.bytes_sent) / dt)
        self._last_net_io = net_io
        self._last_net_time = now

        # ---------------------------------------------------------
        # 8. Workstation System Context
        # ---------------------------------------------------------
        power_profile = await self.get_active_power_profile()
        uptime_sec = int(now - self._boot_time)
        process_count = len(psutil.pids())

        # No memoization on purpose: rates (disk, network) are deltas
        # between this call and the previous one, so every call recomputes.
        # The old `_cached_telemetry` field suggested a cache that never
        # hit -- it was written and returned, never read back.
        return {
            "timestamp": now,
            "cpu": {
                "percent": cpu_percent,
                "cores": cpu_per_core,
                "cores_detail": cores_detail,
                "freq_mhz": round(cpu_freq.current) if cpu_freq else 0,
                "temp_tctl_c": cpu_tctl,
                "temp_tccd1_c": cpu_tccd1,
                "governor": cpu_governor,
                "load_avg": [round(x, 2) for x in load_avg]
            },
            "gpu": gpu,
            "motherboard": {
                "socket_temp_c": mb_socket,
                "system_temp_c": mb_system,
                "vrm_temp_c": mb_vrm,
                "chipset_temp_c": mb_chipset,
                "smbus_temp_c": mb_smbus,
                "tsi0_temp_c": mb_tsi0,
                "voltages": mb_voltages
            },
            "storage_nvme": storage_temps,
            "wifi_temp_c": wifi_temp,
            "ram": {
                "total_mb": round(vmem.total / (1024 * 1024)),
                "used_mb": round(vmem.used / (1024 * 1024)),
                "available_mb": round(vmem.available / (1024 * 1024)),
                "cached_mb": round(getattr(vmem, "cached", 0) / (1024 * 1024)),
                "percent": vmem.percent
            },
            "swap": {
                "total_mb": round(swap.total / (1024 * 1024)),
                "used_mb": round(swap.used / (1024 * 1024)),
                "free_mb": round(swap.free / (1024 * 1024)),
                "percent": swap.percent
            },
            "fans": {
                **fans,
                "gpu": gpu.get("fan_rpm", 0)
            },
            "disk": {
                "total_gb": round(disk_root.total / (1024 * 1024 * 1024), 1),
                "used_gb": round(disk_root.used / (1024 * 1024 * 1024), 1),
                "free_gb": round(disk_root.free / (1024 * 1024 * 1024), 1),
                "percent": disk_root.percent,
                "read_bps": disk_read_rate,
                "write_bps": disk_write_rate
            },
            "network": {
                "rx_bps": net_rx_rate,
                "tx_bps": net_tx_rate
            },
            "system": {
                "uptime_seconds": uptime_sec,
                "process_count": process_count,
                "power_profile": power_profile,
                "os": "CachyOS Linux x86_64",
                "de": "KDE Plasma 6 (Wayland)"
            }
        }
