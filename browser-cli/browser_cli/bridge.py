"""Native messaging bridge that connects browser extension and CLI."""

import asyncio
import base64
import json
import logging
import mimetypes
import struct
import sys
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class NativeMessagingBridge:
    """Bridge between browser extension (native messaging) and CLI (Unix socket)."""

    def __init__(self) -> None:
        """Initialize the bridge."""
        self.cli_clients: set[tuple[asyncio.StreamReader, asyncio.StreamWriter]] = set()
        self.pending_responses: dict[str, asyncio.Future[Any]] = {}
        self.message_counter = 0
        self.stdin_reader: asyncio.StreamReader | None = None
        self.stdout_writer: asyncio.StreamWriter | None = None
        # No tab-ID tracking here. The bridge is a dumb pipe; the
        # extension is the single source of truth for tab state. Caching
        # a tab ID here caused stale-reference bugs after browser restart.

    async def setup_native_messaging(self) -> None:
        """Set up stdin/stdout for native messaging."""
        loop = asyncio.get_event_loop()

        # Create stream reader for stdin
        self.stdin_reader = asyncio.StreamReader()
        stdin_protocol = asyncio.StreamReaderProtocol(self.stdin_reader)
        await loop.connect_read_pipe(lambda: stdin_protocol, sys.stdin)

        # Create stream writer for stdout
        stdout_transport, stdout_protocol = await loop.connect_write_pipe(
            asyncio.streams.FlowControlMixin,
            sys.stdout,
        )
        self.stdout_writer = asyncio.StreamWriter(stdout_transport, stdout_protocol, None, loop)

    async def read_native_message(self) -> dict[str, Any] | None:
        """Read a message from native messaging stdin."""
        if not self.stdin_reader:
            return None

        try:
            # Read message length (4 bytes, little-endian)
            length_bytes = await self.stdin_reader.readexactly(4)
            length = struct.unpack("<I", length_bytes)[0]

            # Read message body
            message_bytes = await self.stdin_reader.readexactly(length)
            message_data: dict[str, Any] = json.loads(message_bytes.decode("utf-8"))
        except asyncio.IncompleteReadError:
            logger.info("Native messaging input closed")
            return None
        except Exception:
            logger.exception("Error reading native message")
            return None
        else:
            return message_data

    async def write_native_message(self, message: dict[str, Any]) -> None:
        """Write a message to native messaging stdout."""
        if not self.stdout_writer:
            return

        try:
            # Encode message
            message_bytes = json.dumps(message).encode("utf-8")

            # Write message length (4 bytes, little-endian)
            self.stdout_writer.write(struct.pack("<I", len(message_bytes)))

            # Write message body
            self.stdout_writer.write(message_bytes)

            await self.stdout_writer.drain()
        except Exception:
            logger.exception("Error writing native message")

    async def process_screenshot_response(
        self,
        response: dict[str, Any],
        output_path: str | None = None,
    ) -> dict[str, Any]:
        """Process screenshot response - save to file and return path."""
        try:
            # Get data URL from response
            data_url = response["result"]["screenshot"]
            if not data_url.startswith("data:image/png;base64,"):
                return response  # Return unchanged if not base64 PNG

            # Extract and decode base64 data
            base64_data = data_url.split(",")[1]
            image_data = base64.b64decode(base64_data)

            # Use provided output path or generate default
            if output_path:
                screenshot_path = Path(output_path)
                # Create parent directory if it doesn't exist
                screenshot_path.parent.mkdir(parents=True, exist_ok=True)
            else:
                # Fallback to current directory
                screenshot_path = Path.cwd() / "screenshot.png"

            # Save screenshot
            screenshot_path.write_bytes(image_data)
            logger.info("Saved screenshot to: %s", screenshot_path)

            # Return modified response with file path instead of data
            return {
                "id": response.get("id"),
                "success": True,
                "result": {
                    "screenshot_path": str(screenshot_path),
                    "message": f"Screenshot saved to {screenshot_path}",
                },
            }
        except Exception as e:
            logger.exception("Error processing screenshot")
            return {
                "id": response.get("id"),
                "success": False,
                "error": f"Failed to save screenshot: {e!s}",
            }

    async def handle_extension_message(self, message: dict[str, Any]) -> None:
        """Process messages from browser extension."""
        msg_id = message.get("id")
        command = message.get("command")

        # Handle commands from extension (e.g., save-screenshot from content script)
        if command == "save-screenshot":
            await self._handle_save_screenshot(message)
            return
        if command == "read-files":
            await self._handle_read_files(message)
            return

        if msg_id and msg_id in self.pending_responses:
            # This is a response to a CLI request
            future = self.pending_responses.pop(msg_id)

            future.set_result(message)
        else:
            # This is a command from the extension - shouldn't happen in our architecture
            logger.warning("Unexpected command from extension: %s", message)

    async def _handle_save_screenshot(self, message: dict[str, Any]) -> None:
        """Handle save-screenshot command from extension."""
        msg_id = message.get("id")
        params = message.get("params", {})
        data_url = params.get("screenshot", "")
        output_path = params.get("output_path")

        if not data_url.startswith("data:image/png;base64,"):
            await self.write_native_message(
                {
                    "id": msg_id,
                    "success": False,
                    "error": "Invalid screenshot data URL",
                },
            )
            return

        try:
            # Extract and decode base64 data
            base64_data = data_url.split(",")[1]
            image_data = base64.b64decode(base64_data)

            # Use provided output path or generate default
            if output_path:
                screenshot_path = Path(output_path)
                screenshot_path.parent.mkdir(parents=True, exist_ok=True)
            else:
                screenshot_path = Path.cwd() / "screenshot.png"

            # Save screenshot
            screenshot_path.write_bytes(image_data)
            logger.info("Saved screenshot to: %s", screenshot_path)

            # Send success response back to extension
            await self.write_native_message(
                {
                    "id": msg_id,
                    "success": True,
                    "result": {
                        "screenshot_path": str(screenshot_path),
                        "message": f"Screenshot saved to {screenshot_path}",
                    },
                },
            )
        except Exception as e:
            logger.exception("Error saving screenshot")
            await self.write_native_message(
                {
                    "id": msg_id,
                    "success": False,
                    "error": f"Failed to save screenshot: {e!s}",
                },
            )

    async def _handle_read_files(self, message: dict[str, Any]) -> None:
        """Read files from disk for upload(). Ships content as base64.

        Native messaging caps a single message at 1 MB, so this rejects
        anything that would push the response past that. Uploading a 50 MB
        video is out of scope; uploading a CSV/PNG/PDF is the use case.
        """
        msg_id = message.get("id")
        paths = message.get("params", {}).get("paths", [])
        result, error = self._read_files_for_upload(paths)
        if error is None:
            await self.write_native_message(
                {"id": msg_id, "success": True, "result": result},
            )
        else:
            await self.write_native_message(
                {"id": msg_id, "success": False, "error": error},
            )

    @staticmethod
    def _read_files_for_upload(
        paths: list[str],
    ) -> tuple[list[dict[str, str]], str | None]:
        """Load and base64-encode files within the native-messaging size budget."""
        # Leave headroom for the JSON envelope around the base64 payload.
        budget = 900_000
        files: list[dict[str, str]] = []
        for raw in paths:
            p = Path(raw).expanduser()
            try:
                data = p.read_bytes()
            except OSError as e:
                return [], f"{raw}: {e}"
            b64 = base64.b64encode(data).decode("ascii")
            budget -= len(b64)
            if budget < 0:
                return [], (f"File(s) too large for native messaging (~1MB limit): {raw}")
            mime, _ = mimetypes.guess_type(p.name)
            files.append(
                {
                    "name": p.name,
                    "mime": mime or "application/octet-stream",
                    "data": b64,
                },
            )
        return files, None

    async def handle_cli_client(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
    ) -> None:
        """Handle connection from CLI client."""
        logger.info("CLI client connected")
        client = (reader, writer)
        self.cli_clients.add(client)

        try:
            while True:
                # Read JSON line
                line = await reader.readline()
                if not line:
                    break

                await self.handle_cli_message(writer, line.decode("utf-8").strip())

        except Exception:
            logger.exception("Error handling CLI client")
        finally:
            logger.info("CLI client disconnected")
            self.cli_clients.discard(client)
            writer.close()
            await writer.wait_closed()

    async def _send_error_response(
        self,
        writer: asyncio.StreamWriter,
        msg_id: str,
        error: str,
    ) -> None:
        """Send error response to CLI client."""
        error_response = {"error": error, "id": msg_id}
        writer.write((json.dumps(error_response) + "\n").encode("utf-8"))
        await writer.drain()

    async def _send_response(self, writer: asyncio.StreamWriter, response: dict[str, Any]) -> None:
        """Send response to CLI client."""
        writer.write((json.dumps(response) + "\n").encode("utf-8"))
        await writer.drain()

    async def handle_cli_message(
        self,
        writer: asyncio.StreamWriter,
        message: str,
    ) -> None:
        """Process messages from CLI client."""
        try:
            data = json.loads(message)

            # Use the client's ID or generate one if missing
            msg_id = data.get("id")
            if not msg_id:
                msg_id = f"cli_{self.message_counter}"
                self.message_counter += 1
                data["id"] = msg_id

            # Create future for response
            future: asyncio.Future[Any] = asyncio.Future()
            self.pending_responses[msg_id] = future

            # Forward to extension via native messaging
            await self.write_native_message(data)

            # Wait for response with timeout
            try:
                response = await asyncio.wait_for(future, timeout=30.0)

                # Special handling for screenshot command
                command = data.get("command", "")
                if (
                    command == "screenshot"
                    and response.get("success")
                    and response.get("result", {}).get("screenshot")
                ):
                    output_path = data.get("params", {}).get("output_path")
                    response = await self.process_screenshot_response(response, output_path)

                await self._send_response(writer, response)
            except TimeoutError:
                self.pending_responses.pop(msg_id, None)
                await self._send_error_response(writer, msg_id, "Request timeout")

        except json.JSONDecodeError:
            logger.exception("Invalid JSON from CLI: %s", message)
            await self._send_response(writer, {"error": "Invalid JSON"})

    async def native_messaging_loop(self) -> None:
        """Handle native messaging in a loop."""
        # setup_native_messaging() is called by start() before we get
        # here so that the ready message can be sent first.
        if not self.stdin_reader:
            await self.setup_native_messaging()

        while True:
            message = await self.read_native_message()
            if message is None:
                break

            await self.handle_extension_message(message)

    async def start(self, socket_path: Path) -> None:
        """Start the bridge server."""
        # Remove old socket if exists
        socket_path.unlink(missing_ok=True)

        # Start Unix socket server for CLI
        server = await asyncio.start_unix_server(
            self.handle_cli_client,
            socket_path,
        )

        # Set socket permissions
        socket_path.chmod(0o600)

        # Set up native messaging BEFORE sending the ready message,
        # otherwise stdout_writer is None and the message is silently
        # dropped (the extension never learns the socket path).
        await self.setup_native_messaging()

        # Send socket path to extension via native messaging
        await self.write_native_message(
            {
                "socket_path": str(socket_path),
                "ready": True,
            },
        )

        logger.info("Native messaging bridge started")
        logger.info("CLI socket: %s", socket_path)

        # Run native messaging loop
        try:
            await self.native_messaging_loop()
        finally:
            # Clean shutdown
            server.close()
            await server.wait_closed()
            socket_path.unlink(missing_ok=True)
