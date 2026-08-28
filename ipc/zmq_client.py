import zmq


class ZmqClient:
    def __init__(self, endpoint: str):
        self.context = zmq.Context()
        self.socket = self.context.socket(zmq.REQ)
        self.socket.connect(endpoint)

    def request(self, command: dict, timeout: float) -> dict:
        self.socket.send_json(command)

        if self.socket.poll(int(timeout * 1000)):
            return self.socket.recv_json()

        raise TimeoutError(
            f"Timeout waiting for response ({timeout}s)"
        )

    def close(self):
        self.socket.close()
        self.context.term()
