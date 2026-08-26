import zmq


class ZmqClient:
    def __init__(self, endpoint: str):
        self.context = zmq.Context()
        self.socket = self.context.socket(zmq.REQ)
        self.socket.connect(endpoint)

    def request(self, command: dict) -> dict:
        self.socket.send_json(command)
        return self.socket.recv_json()

    def close(self):
        self.socket.close()
        self.context.term()
