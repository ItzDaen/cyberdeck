# Author: Daen
# CyberDeck Workstation System Controller
# Platform: CachyOS Linux | KDE Plasma 6 (Wayland) | PipeWire

import asyncio
import json
import logging
import os
import re
import shutil
from pathlib import Path
from typing import Dict, Any, List, Optional

logger = logging.getLogger("cyberdeck.control")

# Where the CyberDeck CLI lives.
#
# Absolute, because this process does not get the user's shell PATH. It is
# a systemd user service: `cyberdeck.service` sets only PYTHONUNBUFFERED, so
# the child inherits systemd's default of /usr/local/bin:/usr/bin and
# nothing else. `cyberhud` is installed to ~/.local/bin and is not on
# that list.
#
# That made the performance buttons look dead rather than broken. Every
# press produced the same line in the journal and nothing on the page:
#
#   Command execution error for cyberhud performance off -q:
#   [Errno 2] No such file or directory: 'cyberhud'
#
# and the state simply did not change, which is indistinguishable from a
# button that is not connected to anything. Five presses, five failures,
# reported to a journal nobody was reading.
#
# The fix is to stop depending on the environment. A path is a fact about
# the installation; PATH is whatever the invoking context felt like, and
# the invoking context here is systemd.
_CYBERHUD_CANDIDATES = (
    Path.home() / ".local" / "bin" / "cyberhud",
    Path("/usr/local/bin/cyberhud"),
    Path("/usr/bin/cyberhud"),
)


def cyberhud() -> str:
    """The absolute path of the CyberDeck CLI, or the bare name as a last resort.

    The last resort is not optimism, it is a better failure: if the CLI
    really is not installed, `ENOENT` names the command, and the log line
    says so. Returning a path that does not exist would turn "not
    installed" into a silent no-op.
    """
    override = os.environ.get("CYBERDECK_CYBERHUD")
    if override:
        return override
    for path in _CYBERHUD_CANDIDATES:
        if path.is_file() and os.access(path, os.X_OK):
            return str(path)
    return "cyberhud"


class SystemController:
    """Safe, asynchronous controller for workstation actions, KDE Plasma session, and system power."""

    def __init__(self, launchers: Optional[List[Dict[str, Any]]] = None):
        self.launchers = {l["id"]: l for l in (launchers or []) if "id" in l and "command" in l}
        # The last failure, carried in the state rather than in the action's
        # return value.
        #
        # The browser sends actions over the WebSocket and never reads a
        # reply, so a command that failed was invisible on the page: the
        # state came back unchanged a second later and a dead switch looks
        # exactly like a switch that was ignored. The state is broadcast
        # every second, so a field on it is the one channel the page is
        # guaranteed to read.
        self.last_error: Optional[str] = None

    def update_launchers(self, launchers: List[Dict[str, Any]]):
        self.launchers = {l["id"]: l for l in (launchers or []) if "id" in l and "command" in l}

    async def _run_command(self, cmd: List[str], timeout: float = 6.0) -> bool:
        """Execute a safe system command asynchronously with timeout."""
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
            if proc.returncode == 0:
                return True
            logger.warning(f"Command {' '.join(cmd)} failed with code {proc.returncode}: {stderr.decode().strip()}")
            return False
        except asyncio.TimeoutError:
            logger.error(f"Command {' '.join(cmd)} timed out after {timeout}s")
            return False
        except Exception as e:
            logger.error(f"Command execution error for {' '.join(cmd)}: {e}")
            return False

    # -------------------------------------------------------------
    # Power Profiles (powerprofilesctl)
    # -------------------------------------------------------------
    async def set_power_profile(self, profile: str) -> bool:
        """Set active system power profile (performance, balanced, power-saver)."""
        valid_profiles = ("performance", "balanced", "power-saver")
        clean_profile = profile.strip().lower()
        if clean_profile not in valid_profiles:
            logger.warning(f"Invalid power profile requested: {profile}")
            return False

        return await self._run_command(["powerprofilesctl", "set", clean_profile])

    # -------------------------------------------------------------
    # Performance mode (the audio spectrum yields to an animated wallpaper)
    # -------------------------------------------------------------
    async def set_performance_mode(self, on: bool) -> bool:
        """Ask the CyberDeck CLI to yield, or not.

        Through the CLI and not by writing the files here: the manual
        override and the automatic detector share one implementation, and
        a second writer would be a second opinion about who is allowed
        to change the state.

        Note what this costs. Setting it by hand is a *manual* choice, so
        it writes the marker that stops the automatic detector. That is
        deliberate -- a person outranks a timer -- but it means a toggle in
        this deck is not the same as the detector agreeing. AUTO is how the
        choice is handed back.
        """
        return await self._run_command(
            [cyberhud(), "performance", "on" if on else "off", "-q"]
        )

    def gpu_free_screens(self) -> List[str]:
        """Screens whose animated wallpaper the manual mode is holding off.

        Read from the CLI's own record, so there is one answer and not two
        that can disagree.
        """
        saved = Path.home() / ".cache" / "cyberdeck" / "gpu-free-wallpapers.json"
        if not saved.exists():
            return []
        try:
            data = json.loads(saved.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as e:
            logger.warning(f"cannot read the GPU-free record: {e}")
            return []
        return sorted(str(k) for k in data) if isinstance(data, dict) else []

    async def set_performance_auto(self) -> bool:
        """Hand the decision back to the detector.

        The third state, and the reason the two buttons are two buttons
        rather than a switch: a two-way control has nowhere to put "let the
        detector decide", so a manual choice made once would be permanent.
        The card's own comment claimed the third state existed. It did --
        on the command line, and nowhere else. So the deck offered no way
        out of a choice it offered a way into.
        """
        return await self._run_command([cyberhud(), "performance", "auto", "-q"])

    def performance_mode(self) -> Dict[str, Any]:
        """The yield state, and where it came from.

        Read, not computed here, for the same reason: one implementation
        of the decision. The restart caveat travels with it, because the
        wallpaper only sees the value when plasmashell comes back up.
        """
        cache = Path.home() / ".cache" / "cyberdeck"
        state = {
            "yielding": (cache / "yield").exists(),
            "manual": (cache / "yield-manual").exists(),
            # The wallpaper reads its own configuration, and a running
            # Plasma wallpaper never re-reads it. So a value written now
            # is on screen only after plasmashell restarts, and saying
            # otherwise from a web button would be a lie.
            #
            # A wallpaper *swap* is the exception and is immediate, because
            # it goes through plasmashell and the plugin is recreated. So
            # the flag is about the spectrum, not about the mode.
            "applies_after_restart": True,
            "screens": {},
            "animated": [],
            # Which screens the manual mode has taken an animated wallpaper
            # off, and the failure of the last performance command, if any.
            "gpu_free": self.gpu_free_screens(),
            "error": self.last_error,
        }
        try:
            applet = (Path.home() / ".config"
                      / "plasma-org.kde.plasma.desktop-appletsrc")
            text = applet.read_text(encoding="utf-8", errors="replace")
            for m in re.finditer(r"^\[Containments\]\[(\d+)\]\s*$(.*?)(?=^\[|\Z)",
                                 text, re.M | re.S):
                kind = re.search(r"^plugin=(.*)$", m.group(2), re.M)
                if not kind or kind.group(1).strip() != "org.kde.plasma.folder":
                    continue
                wp = re.search(r"^wallpaperplugin=(.*)$", m.group(2), re.M)
                state["screens"][m.group(1)] = wp.group(1).strip() if wp else ""
        except OSError as e:
            logger.warning(f"cannot read the wallpaper state: {e}")

        listing = Path.home() / ".config" / "cyberdeck" / "animated-wallpapers.list"
        if listing.exists():
            for line in listing.read_text(encoding="utf-8",
                                          errors="replace").splitlines():
                line = line.split("#", 1)[0].strip()
                if line:
                    state["animated"].append(line)

        # What is animating on a screen that is not showing ours. Reported,
        # never acted on: the performance mode is the user's to throw and
        # nothing automatic throws it. The name is the point -- it used to
        # be "detected" and the page drew it next to a "DECIDED BY
        # detector" line, which said out loud that a timer was in charge of
        # the desktop.
        ours = {cid for cid, wp in state["screens"].items()
                if wp == "cyberdeck.instrument.field"}
        state["animating_elsewhere"] = sorted({
            wp for cid, wp in state["screens"].items()
            if wp in state["animated"] and cid not in ours})
        return state

    # -------------------------------------------------------------
    # Display & Session (KDE Wayland)
    # -------------------------------------------------------------
    async def lock_session(self) -> bool:
        """Lock the current graphical session immediately."""
        return await self._run_command(["loginctl", "lock-session"])

    async def set_display_dpms(self, state: str = "off") -> bool:
        """Turn display power management off (sleep screens) or on."""
        target = "off" if state.lower() in ("off", "sleep", "standby") else "on"
        kscreen_bin = shutil.which("kscreen-doctor")
        if kscreen_bin:
            return await self._run_command([kscreen_bin, "--dpms", target])
        return False

    async def switch_virtual_desktop(self, direction: str) -> bool:
        """Navigate KDE Plasma virtual desktops (next / previous)."""
        method = "nextDesktop" if direction.lower() == "next" else "previousDesktop"
        return await self._run_command([
            "qdbus6", "org.kde.KWin", "/KWin", f"org.kde.KWin.{method}"
        ])

    # -------------------------------------------------------------
    # System Power Management
    # -------------------------------------------------------------
    async def suspend_system(self) -> bool:
        """Suspend the workstation."""
        return await self._run_command(["systemctl", "suspend"])

    async def reboot_system(self) -> bool:
        """Reboot the workstation safely."""
        return await self._run_command(["systemctl", "reboot"])

    async def poweroff_system(self) -> bool:
        """Power off the workstation safely."""
        return await self._run_command(["systemctl", "poweroff"])

    # -------------------------------------------------------------
    # Custom Application Launchers (Extensible by Daen)
    # -------------------------------------------------------------
    async def launch_app(self, app_id: str) -> bool:
        """Launch a pre-configured application asynchronously."""
        if app_id not in self.launchers:
            logger.warning(f"Requested app launcher '{app_id}' not found in configuration")
            return False

        launcher = self.launchers[app_id]
        cmd_str = launcher.get("command", "").strip()
        if not cmd_str:
            return False

        try:
            # Spawn detached process in user session
            proc = await asyncio.create_subprocess_shell(
                cmd_str,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
                start_new_session=True
            )
            logger.info(f"Launched application '{app_id}': {cmd_str} (PID: {proc.pid})")
            return True
        except Exception as e:
            logger.error(f"Failed to launch app '{app_id}': {e}")
            return False
