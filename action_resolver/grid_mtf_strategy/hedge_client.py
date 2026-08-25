import socket
from dataclasses import dataclass


@dataclass
class CommandResult:
    success: bool
    message: str


class HedgeClient:
    def __init__(self, socket_path):
        self.socket_path = socket_path

    def send(self, command: str, timeout: float) -> CommandResult:
        client = socket.socket(
            socket.AF_UNIX,
            socket.SOCK_STREAM,
        )

        try:
            client.settimeout(timeout)

            client.connect(self.socket_path)
            client.sendall((command + "\n").encode())

            data = client.recv(4096)

            if not data:
                return CommandResult(
                    success=False,
                    message="Hedge2 closed connection without response",
                )

            response = data.decode().strip()

            if response == "DONE":
                return CommandResult(
                    success=True,
                    message=response,
                )

            return CommandResult(
                success=False,
                message=response,
            )

        except Exception as e:
            return CommandResult(
                success=False,
                message=str(e),
            )

        finally:
            client.close()
