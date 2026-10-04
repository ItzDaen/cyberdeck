# Author: Daen
# CyberDeck Workstation Core Server v1.0
# Platform: CachyOS Linux | KDE Plasma 6 (Wayland) | PipeWire | Tailscale | Caddy HTTPS

import asyncio
import json
import logging
import os
import signal
import urllib.parse
from pathlib import Path
from typing import Dict, Any, Set, Optional

import yaml
from wsproto import WSConnection, ConnectionType
from wsproto.events import (
    Request,
    AcceptConnection,
    CloseConnection,
    TextMessage,
    Ping,
)

from auth import get_or_create_auth_token, get_tailscale_ip, verify_token
from audio import AudioManager
from media import MediaManager
from telemetry import TelemetryManager
from system_control import SystemController
from visualizer import SpectrumBroadcaster

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("cyberdeck.server")

STATIC_DIR = Path(__file__).parent / "static"
CONFIG_PATH = Path.home() / ".config" / "cyberdeck" / "config.yaml"
# Machine-local overrides. Same directory, never committed, and never
# overwritten by tools/sync-packages.sh.
LOCAL_CONFIG_PATH = CONFIG_PATH.with_name("config.local.yaml")


def _merge(base: Dict[str, Any], over: Dict[str, Any]) -> Dict[str, Any]:
    """Recursively merge `over` into a copy of `base`.

    Two dicts at the same key merge; anything else, including a list, is
    replaced. Returning a copy matters: `base` is the parsed
    config.yaml, and mutating it in place would make the merge
    irreversible if a caller ever merged twice.
    """
    out = dict(base)
    for key, value in over.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _merge(out[key], value)
        else:
            out[key] = value
    return out


class WebSocketClient:
    def __init__(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter, ws: WSConnection):
        self.reader = reader
        self.writer = writer
        self.ws = ws
        self.is_authenticated = False

    async def send_json(self, data: Dict[str, Any]):
        try:
            msg = json.dumps(data)
            output = self.ws.send(TextMessage(data=msg))
            self.writer.write(output)
            await self.writer.drain()
        except Exception:
            pass

    async def close(self):
        try:
            output = self.ws.send(CloseConnection(code=1000, reason="Normal Closure"))
            self.writer.write(output)
            await self.writer.drain()
            self.writer.close()
            await self.writer.wait_closed()
        except Exception:
            pass


def _parse_bool(value: Any) -> bool:
    """A bool from JSON that may arrive as bool, number or string.

    `bool("false")` is True, so raw bool() is wrong for every string form.
    True: True, 1, "1", "true", "yes", "on". Everything else is False.
    """
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        return value.strip().lower() in ("1", "true", "yes", "on")
    return False


class CyberDeckServer:
    def __init__(self):
        self.token = get_or_create_auth_token()
        self.tailscale_ip = get_tailscale_ip()
        self.config = self.load_config()
        self.audio = AudioManager()
        self.media = MediaManager(self.config.get("macros", []))
        self.telemetry = TelemetryManager()
        self.system = SystemController(self.config.get("launchers", []))
        self.spectrum = SpectrumBroadcaster()
        self.ws_clients: Set[WebSocketClient] = set()
        self.https_port = self.config.get("server", {}).get("port", 8765)
        self.backend_port = self.config.get("server", {}).get("backend_port", 8763)
        self.servers = []

    def load_config(self) -> Dict[str, Any]:
        """config.yaml, with config.local.yaml merged over it.

        Two layers, and the reason is the same as .gitignore's: the
        first is versioned and holds what the project means, the second
        holds what this machine means and is never committed. The tailnet
        name of one laptop belongs in the second; with only one layer it
        either leaks into the repository or is lost on the next deploy,
        since `tools/sync-packages.sh` treats config.yaml as a source of
        truth and overwrites it.

        A shallow `dict.update` would be wrong: `deck_buttons` and
        `launchers` are lists, and replacing one wholesale is not what
        "override" should mean for a list. Keys merge, values of a
        different type replace.
        """
        base: Dict[str, Any] = {}
        if CONFIG_PATH.exists():
            try:
                with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                    base = yaml.safe_load(f) or {}
            except Exception as e:
                logger.error(f"Error loading config: {e}")

        if not LOCAL_CONFIG_PATH.exists():
            return base

        try:
            with open(LOCAL_CONFIG_PATH, "r", encoding="utf-8") as f:
                local = yaml.safe_load(f) or {}
        except Exception as e:
            logger.error(f"Error loading {LOCAL_CONFIG_PATH.name}: {e}")
            return base

        return _merge(base, local)

    async def get_full_state(self, audio_state: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        # `audio_state` is the fresh reading the event subscriber just took.
        # Passing it in skips re-querying pactl for what was measured a
        # moment ago; the 1 Hz loop passes nothing and reads everything.
        if audio_state is None:
            audio_state = await self.audio.get_state()
        players = await self.media.get_players()
        telemetry_state = await self.telemetry.get_telemetry()
        return {
            "audio": audio_state,
            "players": players,
            "telemetry": telemetry_state,
            "performance": self.system.performance_mode(),
            "deck_buttons": self.config.get("deck_buttons", []),
            "macros": self.config.get("macros", []),
            "launchers": self.config.get("launchers", [])
        }

    async def broadcast_state(self, state: Optional[Dict[str, Any]] = None):
        # `state` is the audio reading the subscriber just took: it travels
        # into the payload instead of being thrown away and re-queried.
        # Anything else still comes from a fresh read. Callers that have no
        # fresh reading pass nothing, as the 1 Hz loop does.
        audio_state = state if isinstance(state, dict) else None
        full_payload = await self.get_full_state(audio_state=audio_state)
        payload = {
            "type": "state_update",
            **full_payload
        }

        tasks = []
        for client in list(self.ws_clients):
            if client.is_authenticated:
                tasks.append(client.send_json(payload))
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    async def handle_action(self, action_data: Dict[str, Any]) -> Dict[str, Any]:
        """Dispatch whitelisted deck actions."""
        action_type = action_data.get("type", "")
        target = action_data.get("target", "")

        logger.info(f"Executing action: {action_type} target: {target}")

        # Audio Sources (Mics)
        if action_type == "source_mute_toggle":
            success = await self.audio.toggle_source_mute(target)
            return {"success": success}
        elif action_type == "source_mute_set":
            mute = _parse_bool(action_data.get("mute", False))
            success = await self.audio.set_source_mute(target, mute)
            return {"success": success}
        elif action_type == "source_volume_set":
            vol = int(action_data.get("volume", 100))
            success = await self.audio.set_source_volume(target, vol)
            return {"success": success}

        # Audio Sinks (Speakers/Outputs)
        elif action_type == "sink_mute_toggle":
            success = await self.audio.toggle_sink_mute(target)
            return {"success": success}
        elif action_type == "sink_mute_set":
            mute = _parse_bool(action_data.get("mute", False))
            success = await self.audio.set_sink_mute(target, mute)
            return {"success": success}
        elif action_type == "sink_volume_set":
            vol = int(action_data.get("volume", 100))
            success = await self.audio.set_sink_volume(target, vol)
            return {"success": success}

        # Global Audio Kill Switch
        elif action_type == "mute_all_mics":
            raw = action_data.get("mute")
            mute_state = None if raw is None else _parse_bool(raw)
            res = await self.audio.mute_all_mics(mute_state)
            return {"success": True, "muted": res}

        # Discord Specific Toggles
        elif action_type == "discord_mic_toggle":
            success = await self.audio.toggle_discord_mic_mute()
            return {"success": success}
        elif action_type == "discord_audio_toggle":
            success = await self.audio.toggle_discord_audio_mute()
            return {"success": success}

        # Media Player MPRIS Controls
        elif action_type == "media_control":
            act = action_data.get("action", "PlayPause")
            service = action_data.get("service")
            success = await self.media.execute_media_action(act, service)
            return {"success": success}
        elif action_type == "media_seek":
            service = action_data.get("service", "")
            if "offset" in action_data:
                offset = float(action_data.get("offset", 0.0))
                success = await self.media.seek_offset(service, offset)
            else:
                pos = float(action_data.get("position", 0.0))
                trackid = action_data.get("trackid")
                success = await self.media.set_player_position(service, pos, trackid)
            return {"success": success}
        elif action_type == "media_volume":
            service = action_data.get("service", "")
            vol = int(action_data.get("volume", 100))
            success = await self.media.set_player_volume(service, vol)
            return {"success": success}

        # Custom Macros
        elif action_type == "macro":
            macro_id = action_data.get("macro_id", "")
            success = await self.media.execute_macro(macro_id)
            return {"success": success}

        # Workstation System Controls
        elif action_type == "power_profile_set":
            profile = action_data.get("profile", "balanced")
            success = await self.system.set_power_profile(profile)
            return {"success": success}
        elif action_type == "performance_mode_set":
            # Parsed, not coerced: `bool("false")` is True in Python, so a
            # raw bool() here turned every string -- including "false",
            # "0" and "off" -- into ON. That is a GPU switch; it gets a
            # parser.
            on = _parse_bool(action_data.get("on", False))
            success = await self.system.set_performance_mode(on)
            # Kept on the controller, not only in the reply: the page sends
            # over the WebSocket and never reads a reply, so a failure has
            # to travel with the state it broadcasts every second or it
            # does not exist as far as the user is concerned.
            self.system.last_error = (
                None if success else
                "the cyberhud command failed; see the server journal"
            )
            return {"success": success, **self.system.performance_mode()}
        elif action_type == "performance_mode_auto":
            success = await self.system.set_performance_auto()
            self.system.last_error = (
                None if success else
                "the cyberhud command failed; see the server journal"
            )
            return {"success": success, **self.system.performance_mode()}
        elif action_type == "session_lock":
            success = await self.system.lock_session()
            return {"success": success}
        elif action_type == "display_dpms":
            state = action_data.get("state", "off")
            success = await self.system.set_display_dpms(state)
            return {"success": success}
        elif action_type == "desktop_nav":
            direction = action_data.get("direction", "next")
            success = await self.system.switch_virtual_desktop(direction)
            return {"success": success}
        elif action_type == "system_power":
            sub_action = action_data.get("action", "")
            if sub_action == "suspend":
                success = await self.system.suspend_system()
            elif sub_action == "reboot":
                success = await self.system.reboot_system()
            elif sub_action == "poweroff":
                success = await self.system.poweroff_system()
            else:
                raise ValueError(f"Unknown system power action: {sub_action}")
            return {"success": success}
        elif action_type == "launch_app":
            app_id = action_data.get("app_id", "")
            success = await self.system.launch_app(app_id)
            return {"success": success}
        else:
            raise ValueError(f"Unknown action type: {action_type}")

    def check_auth(self, headers: Dict[str, str], query_params: Dict[str, str]) -> bool:
        if "token" in query_params and verify_token(query_params["token"], self.token):
            return True
        auth_header = headers.get("authorization", "")
        if auth_header.startswith("Bearer "):
            token = auth_header[7:].strip()
            if verify_token(token, self.token):
                return True
        cookie_header = headers.get("cookie", "")
        if cookie_header:
            cookies = dict(c.strip().split("=", 1) for c in cookie_header.split(";") if "=" in c)
            if "auth_token" in cookies and verify_token(cookies["auth_token"], self.token):
                return True
        return False

    async def handle_http_request(self, method: str, path: str, headers: Dict[str, str], body: bytes, writer: asyncio.StreamWriter):
        parsed_url = urllib.parse.urlparse(path)
        req_path = parsed_url.path
        query_params = dict(urllib.parse.parse_qsl(parsed_url.query))

        is_auth = self.check_auth(headers, query_params)

        def send_response(status: int, content_type: str, data: bytes, extra_headers: Optional[Dict[str, str]] = None):
            # Only the codes this server actually sends. `400` was missing and
            # `.get(status, "OK")` turned every rejected action into the literal
            # status line `HTTP/1.1 400 OK`. fetch() reads the code, so the browser
            # did not care; every other client and every log line did.
            status_text = {200: "OK", 400: "Bad Request", 401: "Unauthorized",
                           404: "Not Found", 405: "Method Not Allowed",
                           413: "Content Too Large",
                           500: "Internal Server Error"}
            h = {
                "Content-Type": content_type,
                "Content-Length": str(len(data)),
                "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
                "Access-Control-Allow-Headers": "Content-Type, Authorization",
                "X-Content-Type-Options": "nosniff",
                "X-Frame-Options": "SAMEORIGIN",
                "Strict-Transport-Security": "max-age=31536000; includeSubDomains; preload",
                "Connection": "close"
            }
            if extra_headers:
                h.update(extra_headers)

            hdr_lines = [f"HTTP/1.1 {status} {status_text.get(status, 'Error')}"] + [f"{k}: {v}" for k, v in h.items()]
            writer.write(("\r\n".join(hdr_lines) + "\r\n\r\n").encode("utf-8") + data)

        if method == "OPTIONS":
            send_response(200, "text/plain", b"")
            await writer.drain()
            return

        if req_path in ("/", "/index.html"):
            if not is_auth:
                send_response(401, "application/json", json.dumps({"error": "Unauthorized"}).encode("utf-8"))
                await writer.drain()
                return
            index_path = STATIC_DIR / "index.html"
            if index_path.exists():
                content = index_path.read_text(encoding="utf-8")
                send_response(200, "text/html; charset=utf-8", content.encode("utf-8"), {
                    "Set-Cookie": f"auth_token={self.token}; Path=/; HttpOnly; Secure; SameSite=Lax; Max-Age=31536000"
                })
            else:
                send_response(404, "text/plain", b"index.html not found")
            await writer.drain()
            return

        if req_path.startswith("/static/"):
            file_name = os.path.basename(req_path)
            file_path = STATIC_DIR / file_name
            if file_path.exists() and file_path.is_file():
                ext = file_path.suffix.lower()
                mime = {
                    ".html": "text/html",
                    ".js": "application/javascript",
                    ".css": "text/css",
                    ".json": "application/json",
                    ".png": "image/png",
                    ".svg": "image/svg+xml",
                    ".ico": "image/x-icon"
                }.get(ext, "application/octet-stream")
                send_response(200, mime, file_path.read_bytes())
            else:
                send_response(404, "text/plain", b"File not found")
            await writer.drain()
            return

        if req_path == "/manifest.json":
            m_path = STATIC_DIR / "manifest.json"
            if m_path.exists():
                send_response(200, "application/manifest+json", m_path.read_bytes())
            else:
                send_response(404, "text/plain", b"manifest.json not found")
            await writer.drain()
            return

        if req_path in ("/icon.svg", "/favicon.ico"):
            # The tab icon. index.html links `icon.svg` which resolves to
            # `/icon.svg` from `/`; the manifest already uses
            # `/static/icon.svg`. Both serve the same file, publicly like the
            # other static assets: no secret in an icon.
            i_path = STATIC_DIR / "icon.svg"
            if i_path.exists():
                send_response(200, "image/svg+xml", i_path.read_bytes())
            else:
                send_response(404, "text/plain", b"icon.svg not found")
            await writer.drain()
            return

        if req_path == "/sw.js":
            sw_path = STATIC_DIR / "sw.js"
            if sw_path.exists():
                send_response(200, "application/javascript", sw_path.read_bytes())
            else:
                send_response(404, "text/plain", b"sw.js not found")
            await writer.drain()
            return

        if not is_auth:
            send_response(401, "application/json", json.dumps({"error": "Unauthorized"}).encode("utf-8"))
            await writer.drain()
            return

        if req_path == "/api/state" and method == "GET":
            payload = await self.get_full_state()
            send_response(200, "application/json", json.dumps(payload).encode("utf-8"))
            await writer.drain()
            return

        if ((req_path == "/api/state" and method != "GET")
                or (req_path == "/api/action" and method != "POST")):
            # Right path, wrong verb: 405, not 404. A POST to /api/state or
            # a GET to /api/action used to read as "not found", which sent
            # debugging down the wrong path.
            send_response(405, "application/json",
                          json.dumps({"error": "Method Not Allowed"}).encode("utf-8"),
                          {"Allow": "GET, POST"})
            await writer.drain()
            return

        if req_path == "/api/action" and method == "POST":
            try:
                data = json.loads(body.decode("utf-8"))
                if data.get("type") == "action" and "data" in data and isinstance(data["data"], dict):
                    data = data["data"]
                res = await self.handle_action(data)
                send_response(200, "application/json", json.dumps(res).encode("utf-8"))
            except Exception as e:
                send_response(400, "application/json", json.dumps({"error": str(e)}).encode("utf-8"))
            await writer.drain()
            return

        send_response(404, "text/plain", b"Not Found")
        await writer.drain()

    async def handle_connection(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        try:
            req_data = b""
            while b"\r\n\r\n" not in req_data:
                chunk = await reader.read(4096)
                if not chunk:
                    break
                req_data += chunk

            if not req_data:
                writer.close()
                await writer.wait_closed()
                return

            header_part, rest = req_data.split(b"\r\n\r\n", 1)
            lines = header_part.decode("utf-8", errors="ignore").split("\r\n")
            # split() always returns at least [""], so `if not lines` could
            # never fire. The real malformed case is a request line with
            # fewer than two tokens, checked below.

            req_line = lines[0].split(" ")
            if len(req_line) < 2:
                writer.close()
                await writer.wait_closed()
                return

            method, path = req_line[0], req_line[1]
            headers = {}
            for l in lines[1:]:
                if ": " in l:
                    k, v = l.split(": ", 1)
                    headers[k.lower()] = v.strip()

            parsed_url = urllib.parse.urlparse(path)
            query_params = dict(urllib.parse.parse_qsl(parsed_url.query))

            # WebSocket upgrade check. The path matters: without it any path
            # with `Upgrade: websocket` became a socket, and a plain
            # `GET /ws` fell through to 404 with no hint. The client
            # connects to /ws and only there.
            if headers.get("upgrade", "").lower() == "websocket" and parsed_url.path == "/ws":
                ws = WSConnection(ConnectionType.SERVER)
                client = WebSocketClient(reader, writer, ws)

                is_auth = self.check_auth(headers, query_params)
                if not is_auth:
                    writer.write(b"HTTP/1.1 401 Unauthorized\r\n"
                                 b"Content-Length: 0\r\n"
                                 b"Connection: close\r\n\r\n")
                    await writer.drain()
                    writer.close()
                    await writer.wait_closed()
                    return

                client.is_authenticated = True

                ws.receive_data(req_data)
                for ev in ws.events():
                    if isinstance(ev, Request):
                        output = ws.send(AcceptConnection())
                        writer.write(output)
                        await writer.drain()

                self.ws_clients.add(client)
                logger.info("New secure CyberDeck WebSocket client connected and authenticated")

                # Send initial state
                initial_state = await self.get_full_state()
                await client.send_json({
                    "type": "state_update",
                    **initial_state
                })

                try:
                    while True:
                        data = await reader.read(4096)
                        if not data:
                            break
                        ws.receive_data(data)
                        for ws_event in ws.events():
                            if isinstance(ws_event, TextMessage):
                                try:
                                    msg = json.loads(ws_event.data)
                                    msg_type = msg.get("type", "")
                                    if msg_type == "spectrum_subscribe":
                                        await self.spectrum.add_subscriber(client)
                                    elif msg_type == "spectrum_unsubscribe":
                                        await self.spectrum.remove_subscriber(client)
                                    elif msg_type == "ping":
                                        await client.send_json({"type": "pong"})
                                    elif msg_type == "action":
                                        action_payload = msg.get("data", msg)
                                        await self.handle_action(action_payload)
                                        await asyncio.sleep(0.02)
                                        await self.broadcast_state()
                                    elif msg_type:
                                        # Support direct action payload dispatched without "action" envelope
                                        await self.handle_action(msg)
                                        await asyncio.sleep(0.02)
                                        await self.broadcast_state()
                                except Exception as e:
                                    logger.error(f"WS message error: {e}")
                            elif isinstance(ws_event, Ping):
                                output = ws.send(ws_event.response())
                                writer.write(output)
                                await writer.drain()
                            elif isinstance(ws_event, CloseConnection):
                                break
                except Exception as e:
                    logger.debug(f"WS connection closed: {e}")
                finally:
                    await self.spectrum.remove_subscriber(client)
                    self.ws_clients.discard(client)
                    # The close handshake, not a bare TCP close: this is what
                    # WebSocketClient.close() exists for, and nothing called
                    # it -- every exit path closed the writer directly.
                    try:
                        await client.close()
                    except Exception:
                        pass
                return

            try:
                content_len = int(headers.get("content-length", 0))
            except ValueError:
                content_len = 0
            # No unbounded reads: a declared body larger than 1 MiB is
            # refused before a byte of it is buffered. Local network only,
            # but memory is memory.
            if content_len > 1024 * 1024:
                writer.write(b"HTTP/1.1 413 Content Too Large\r\n"
                             b"Content-Length: 0\r\n"
                             b"Connection: close\r\n\r\n")
                await writer.drain()
                writer.close()
                await writer.wait_closed()
                return
            body = rest
            while len(body) < content_len:
                needed = content_len - len(body)
                chunk = await reader.read(min(needed, 4096))
                if not chunk:
                    break
                body += chunk

            await self.handle_http_request(method, path, headers, body, writer)
            writer.close()
            await writer.wait_closed()

        except Exception as e:
            logger.error(f"Error handling connection: {e}")
            try:
                writer.close()
                await writer.wait_closed()
            except Exception:
                pass

    def reload_config(self) -> None:
        """Re-read config.yaml + config.local.yaml without restarting.

        Refreshes the launcher and macro tables in place, so editing them
        no longer needs a service restart. Called on SIGHUP; see
        `systemctl --user reload cyberdeck` and the ExecReload line in
        src/systemd/cyberdeck.service.
        """
        self.config = self.load_config()
        self.system.update_launchers(self.config.get("launchers", []))
        self.media.update_macros(self.config.get("macros", []))
        logger.info("configuration reloaded (launchers, macros)")

    async def run(self):
        backend_host = "127.0.0.1"
        try:
            srv = await asyncio.start_server(
                self.handle_connection, backend_host, self.backend_port
            )
            self.servers.append(srv)
            logger.info(f"CyberDeck Core Backend listening on http://{backend_host}:{self.backend_port}")
        except Exception as e:
            logger.error(f"Failed to bind backend on {backend_host}:{self.backend_port}: {e}")

        self.audio.register_listener(self.broadcast_state)
        asyncio.create_task(self.audio.start_event_subscriber())

        # Unified periodic background broadcast loop for Telemetry and Media sync (1.0 Hz)
        async def telemetry_and_media_sync_loop():
            while True:
                try:
                    if self.ws_clients:
                        await self.broadcast_state()
                except Exception as e:
                    logger.debug(f"Sync loop error: {e}")
                await asyncio.sleep(1.0)

        asyncio.create_task(telemetry_and_media_sync_loop())

        # The address the user reaches this deck on. It was a hardcoded
        # MagicDNS name, which is both a personal detail and a fact about
        # one machine's tailnet: anyone else running this got a banner
        # pointing at a host that is not theirs. It is configuration now,
        # and the banner says so plainly when it is not set.
        magic_dns = self.config.get("server", {}).get("public_host", "").strip()
        try:
            loop = asyncio.get_running_loop()
            loop.add_signal_handler(signal.SIGHUP, self.reload_config)
        except (NotImplementedError, RuntimeError, OSError) as e:
            logger.debug(f"SIGHUP reload not wired: {e}")
        print("=" * 64, flush=True)
        print("  CYBERDECK DASHBOARD v1.0 - VALIDATED HTTPS ACTIVE", flush=True)
        print("=" * 64, flush=True)
        print("  Author       : Daen", flush=True)
        print("  Version      : 1.0", flush=True)
        print("  Auth Token   : <redacted - see ~/.config/cyberdeck/auth.token>", flush=True)
        if magic_dns:
            print(f"  Public URL   : https://{magic_dns}:{self.https_port}/ (token required)", flush=True)
            print(f"  Caddy Proxy  : https://{magic_dns}:{self.https_port} -> http://127.0.0.1:{self.backend_port}", flush=True)
        else:
            print("  Public URL   : not set (server.public_host in config.yaml)", flush=True)
            print(f"  Local URL    : http://127.0.0.1:{self.backend_port}/?token=<token>", flush=True)
        if self.tailscale_ip and self.tailscale_ip != "127.0.0.1":
            print(f"  Tailscale IP : {self.tailscale_ip}", flush=True)
        print("  TLS Status   : Validated Certificate (Let's Encrypt YE2)", flush=True)
        print("=" * 64, flush=True)

        try:
            await asyncio.gather(*[s.serve_forever() for s in self.servers])
        finally:
            await self.shutdown()

    async def shutdown(self):
        """Unhook everything run() hooked up.

        Previously nothing called `SpectrumBroadcaster.cleanup()` or
        `AudioManager.unregister_listener()` -- grep found only the
        definitions -- so a SIGTERM left the cava child running. The
        `finally` above is what calls this on every exit path.
        """
        try:
            self.audio.unregister_listener(self.broadcast_state)
        except Exception:
            pass
        try:
            await self.spectrum.cleanup()
        except Exception as e:
            logger.debug(f"spectrum cleanup: {e}")

if __name__ == "__main__":
    server = CyberDeckServer()
    try:
        asyncio.run(server.run())
    except KeyboardInterrupt:
        print("CyberDeck server stopped.")

