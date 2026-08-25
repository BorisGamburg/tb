import socket


class HedgeServer:
    def __init__(self, socket_path):
        self.socket_path = socket_path

    def serve(self, handler):
        server = socket.socket(
            socket.AF_UNIX,
            socket.SOCK_STREAM,
        )

        server.bind(self.socket_path)
        server.listen()

        while True:
            conn, _ = server.accept()

            try:
                data = conn.recv(4096)

                if not data:
                    continue

                command = data.decode().strip()

                try:
                    handler(command)

                    response = "DONE"

                except Exception as e:
                    response = f"ERROR:{e}"

                conn.sendall(
                    (response + "\n").encode()
                )

            finally:
                conn.close()
