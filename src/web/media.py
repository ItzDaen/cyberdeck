# Author: Daen
# CyberDeck Workstation & Audio System

import asyncio
import json
import logging
from typing import Dict, Any, List, Optional

logger = logging.getLogger("cyberdeck.media")

def _match_player_to_sink(srv: str, identity: str, app_name: str) -> bool:
    srv_l = srv.lower()
    id_l = identity.lower()
    app_l = app_name.lower()
    
    # Check browser family
    browser_keywords = ['firefox', 'wolf', 'librewolf', 'chrome', 'chromium', 'brave', 'edge', 'opera', 'vivaldi', 'browser']
    if any(b in srv_l or b in id_l for b in browser_keywords):
        if any(b in app_l for b in browser_keywords):
            return True
            
    # Generic token match
    tokens = srv_l.replace('org.mpris.mediaplayer2.', '').split('.') + id_l.split(' ')
    for tok in tokens:
        if len(tok) >= 3 and tok in app_l:
            return True
            
    return False

class MediaManager:
    """Manages synchronized MPRIS media player controls, timeline seeking, per-player PipeWire volume, and macros."""

    def __init__(self, macros: Optional[List[Dict[str, Any]]] = None):
        self.macros = {m["id"]: m for m in (macros or []) if "id" in m and "command" in m}

    def update_macros(self, macros: List[Dict[str, Any]]):
        """Replace the macro table without restarting the server.

        Same contract as `SystemController.update_launchers`: called by
        `CyberDeckServer.reload_config()` on SIGHUP.
        """
        self.macros = {m["id"]: m for m in (macros or []) if "id" in m and "command" in m}

    async def _get_sink_inputs(self) -> List[Dict[str, Any]]:
        """Fetch all active PipeWire sink inputs."""
        try:
            proc = await asyncio.create_subprocess_exec(
                "pactl", "-f", "json", "list", "sink-inputs",
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
            )
            stdout, _ = await proc.communicate()
            if proc.returncode == 0 and stdout:
                return json.loads(stdout.decode("utf-8", errors="ignore"))
        except Exception as e:
            logger.debug(f"Error listing sink-inputs: {e}")
        return []

    async def get_players(self) -> List[Dict[str, Any]]:
        """Query all active MPRIS media players with live status, track metadata, timeline position, and PipeWire volume."""
        players_list = []
        try:
            proc = await asyncio.create_subprocess_exec(
                "qdbus6",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, _ = await proc.communicate()
            services = [s.strip() for s in stdout.decode("utf-8").split("\n") if "org.mpris.MediaPlayer2." in s]

            sink_inputs = await self._get_sink_inputs()

            for srv in services:
                try:
                    # Identity
                    id_proc = await asyncio.create_subprocess_exec(
                        "qdbus6", srv, "/org/mpris/MediaPlayer2", "org.mpris.MediaPlayer2.Identity",
                        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
                    )
                    id_out, _ = await id_proc.communicate()
                    identity = id_out.decode("utf-8").strip() or srv.split(".")[-1]

                    # Status
                    st_proc = await asyncio.create_subprocess_exec(
                        "qdbus6", srv, "/org/mpris/MediaPlayer2", "org.mpris.MediaPlayer2.Player.PlaybackStatus",
                        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
                    )
                    st_out, _ = await st_proc.communicate()
                    status = st_out.decode("utf-8").strip() or "Stopped"

                    # Position
                    pos_sec = 0.0
                    try:
                        pos_proc = await asyncio.create_subprocess_exec(
                            "qdbus6", srv, "/org/mpris/MediaPlayer2", "org.mpris.MediaPlayer2.Player.Position",
                            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
                        )
                        pos_out, _ = await pos_proc.communicate()
                        pos_raw = pos_out.decode("utf-8").strip()
                        if pos_raw.isdigit():
                            pos_sec = int(pos_raw) / 1000000.0
                    except Exception:
                        pass

                    # Volume: Check PipeWire sink-input first for true volume
                    vol_percent = 100
                    matched_pipewire_vol = False
                    
                    for inp in sink_inputs:
                        props = inp.get("properties", {})
                        app_name = (props.get("application.name", "") + " " + props.get("application.process.binary", "") + " " + props.get("node.name", ""))
                        if _match_player_to_sink(srv, identity, app_name):
                            vol_dict = inp.get("volume", {}).get("front-left", {})
                            if "value_percent" in vol_dict:
                                pct_str = vol_dict["value_percent"].replace("%", "").strip()
                                try:
                                    vol_percent = int(pct_str)
                                    matched_pipewire_vol = True
                                    break
                                except ValueError:
                                    pass

                    if not matched_pipewire_vol:
                        try:
                            vol_proc = await asyncio.create_subprocess_exec(
                                "qdbus6", srv, "/org/mpris/MediaPlayer2", "org.freedesktop.DBus.Properties.Get", "org.mpris.MediaPlayer2.Player", "Volume",
                                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
                            )
                            vol_out, _ = await vol_proc.communicate()
                            vol_str = vol_out.decode("utf-8").strip()
                            if vol_str:
                                vol_percent = max(0, min(100, int(float(vol_str) * 100)))
                        except Exception:
                            pass

                    # Metadata
                    meta_proc = await asyncio.create_subprocess_exec(
                        "qdbus6", srv, "/org/mpris/MediaPlayer2", "org.mpris.MediaPlayer2.Player.Metadata",
                        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
                    )
                    meta_out, _ = await meta_proc.communicate()
                    meta_raw = meta_out.decode("utf-8").strip().split("\n")
                    
                    title = ""
                    artist = ""
                    art_url = ""
                    length_sec = 0.0
                    trackid = "/org/mpris/MediaPlayer2/TrackList/NoTrack"

                    for line in meta_raw:
                        if line.startswith("xesam:title:"):
                            title = line.split("xesam:title:", 1)[1].strip()
                        elif line.startswith("xesam:artist:"):
                            artist = line.split("xesam:artist:", 1)[1].strip()
                        elif line.startswith("mpris:artUrl:"):
                            # Only URLs the browser can actually fetch. In
                            # practice players report file:// paths, which
                            # load nowhere except the local machine itself
                            # -- on the phone that is a broken-image icon.
                            # http(s) and embedded data: pass through;
                            # anything else becomes absent and the client
                            # shows its note glyph instead.
                            candidate = line.split("mpris:artUrl:", 1)[1].strip()
                            if candidate.startswith(("http://", "https://", "data:")):
                                art_url = candidate
                        elif line.startswith("mpris:length:"):
                            l_val = line.split("mpris:length:", 1)[1].strip()
                            if l_val.isdigit():
                                length_sec = int(l_val) / 1000000.0
                        elif line.startswith("mpris:trackid:"):
                            t_val = line.split("mpris:trackid:", 1)[1].strip()
                            if t_val:
                                trackid = t_val

                    # Can seek check
                    can_seek = True
                    try:
                        cs_proc = await asyncio.create_subprocess_exec(
                            "qdbus6", srv, "/org/mpris/MediaPlayer2", "org.mpris.MediaPlayer2.Player.CanSeek",
                            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
                        )
                        cs_out, _ = await cs_proc.communicate()
                        if cs_out.decode("utf-8").strip().lower() == "false":
                            can_seek = False
                    except Exception:
                        pass

                    players_list.append({
                        "service": srv,
                        "identity": identity,
                        "status": status,
                        "title": title or "Nessuna traccia",
                        "artist": artist or identity,
                        "art_url": art_url,
                        "position": round(pos_sec, 1),
                        "length": round(length_sec, 1),
                        "volume": vol_percent,
                        "trackid": trackid,
                        "can_seek": can_seek,
                        "is_playing": status.lower() == "playing"
                    })
                except Exception as e:
                    logger.debug(f"Error querying player {srv}: {e}")

        except Exception as e:
            logger.error(f"Error listing MPRIS services: {e}")

        return players_list

    async def set_player_volume(self, service: str, volume_percent: int) -> bool:
        """Set player volume across both PipeWire audio streams and MPRIS."""
        if not service or not service.startswith("org.mpris.MediaPlayer2."):
            raise ValueError("Invalid MPRIS service name")

        volume_percent = max(0, min(150, int(volume_percent)))
        vol_float = max(0.0, min(1.0, float(volume_percent) / 100.0))

        success = False

        # 1. Adjust PipeWire sink-inputs matching player
        try:
            sink_inputs = await self._get_sink_inputs()
            
            # Query identity for accurate matching
            id_proc = await asyncio.create_subprocess_exec(
                "qdbus6", service, "/org/mpris/MediaPlayer2", "org.mpris.MediaPlayer2.Identity",
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
            )
            id_out, _ = await id_proc.communicate()
            identity = id_out.decode("utf-8").strip() or service.split(".")[-1]

            for inp in sink_inputs:
                props = inp.get("properties", {})
                app_name = (props.get("application.name", "") + " " + props.get("application.process.binary", "") + " " + props.get("node.name", ""))
                if _match_player_to_sink(service, identity, app_name):
                    idx = str(inp["index"])
                    p = await asyncio.create_subprocess_exec(
                        "pactl", "set-sink-input-volume", idx, f"{volume_percent}%"
                    )
                    await p.communicate()
                    if p.returncode == 0:
                        success = True
        except Exception as e:
            logger.debug(f"PipeWire sink-input volume set error: {e}")

        # 2. Adjust MPRIS DBus Volume
        try:
            p = await asyncio.create_subprocess_exec(
                "qdbus6", service, "/org/mpris/MediaPlayer2", "org.freedesktop.DBus.Properties.Set",
                "org.mpris.MediaPlayer2.Player", "Volume", str(vol_float),
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
            )
            await p.communicate()
            if p.returncode == 0:
                success = True
        except Exception as e:
            logger.debug(f"DBus Set Volume failed: {e}")

        return success

    async def set_player_position(self, service: str, position_sec: float, trackid: Optional[str] = None) -> bool:
        """Seek a media player to a specified timestamp in seconds."""
        if not service.startswith("org.mpris.MediaPlayer2."):
            raise ValueError("Invalid MPRIS service name")

        pos_usec = int(position_sec * 1000000)
        tid = trackid or "/org/mpris/MediaPlayer2/TrackList/NoTrack"

        try:
            p = await asyncio.create_subprocess_exec(
                "qdbus6", service, "/org/mpris/MediaPlayer2", "org.mpris.MediaPlayer2.Player.SetPosition",
                tid, str(pos_usec),
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
            )
            await p.communicate()
            if p.returncode == 0:
                return True
        except Exception as e:
            logger.debug(f"SetPosition failed: {e}")

        try:
            cur_proc = await asyncio.create_subprocess_exec(
                "qdbus6", service, "/org/mpris/MediaPlayer2", "org.mpris.MediaPlayer2.Player.Position",
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
            )
            out, _ = await cur_proc.communicate()
            val = out.decode("utf-8").strip()
            if val.isdigit():
                cur_pos = int(val)
                diff = pos_usec - cur_pos
                p = await asyncio.create_subprocess_exec(
                    "qdbus6", service, "/org/mpris/MediaPlayer2", "org.mpris.MediaPlayer2.Player.Seek",
                    str(diff),
                    stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
                )
                await p.communicate()
                return p.returncode == 0
        except Exception as e:
            logger.debug(f"Seek fallback failed: {e}")

        return False

    async def seek_offset(self, service: str, offset_sec: float) -> bool:
        """Seek forward or backward by offset in seconds."""
        if not service.startswith("org.mpris.MediaPlayer2."):
            raise ValueError("Invalid MPRIS service name")
        diff_usec = int(offset_sec * 1000000)
        try:
            p = await asyncio.create_subprocess_exec(
                "qdbus6", service, "/org/mpris/MediaPlayer2", "org.mpris.MediaPlayer2.Player.Seek",
                str(diff_usec),
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
            )
            await p.communicate()
            return p.returncode == 0
        except Exception as e:
            logger.debug(f"Seek offset failed: {e}")
            return False

    async def execute_media_action(self, action: str, service: Optional[str] = None) -> bool:
        """Send MPRIS commands to a specific player service or all players."""
        valid_actions = {"PlayPause", "Next", "Previous", "Stop", "Play", "Pause"}
        if action not in valid_actions:
            raise ValueError(f"Invalid media action: {action}")

        if service:
            if not service.startswith("org.mpris.MediaPlayer2."):
                raise ValueError("Invalid MPRIS service name")
            try:
                p = await asyncio.create_subprocess_exec(
                    "qdbus6", service, "/org/mpris/MediaPlayer2", f"org.mpris.MediaPlayer2.Player.{action}",
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )
                await p.communicate()
                return p.returncode == 0
            except Exception as e:
                logger.error(f"Error executing action {action} on {service}: {e}")
                return False

        players = await self.get_players()
        if not players:
            return False

        success = False
        target_players = [p["service"] for p in players]
        for srv in target_players:
            p = await asyncio.create_subprocess_exec(
                "qdbus6", srv, "/org/mpris/MediaPlayer2", f"org.mpris.MediaPlayer2.Player.{action}",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            await p.communicate()
            if p.returncode == 0:
                success = True
        return success

    async def execute_macro(self, macro_id: str) -> bool:
        """Safely execute a whitelisted macro command without shell."""
        if macro_id not in self.macros:
            logger.warning(f"Attempted to execute unregistered macro: {macro_id}")
            raise ValueError("Unauthorized or non-existent macro ID")

        cmd = self.macros[macro_id]["command"]
        if not isinstance(cmd, list) or not cmd:
            raise ValueError("Macro command must be a list of arguments")

        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            await proc.communicate()
            return proc.returncode == 0
        except Exception as e:
            logger.error(f"Error executing macro {macro_id}: {e}")
            return False
