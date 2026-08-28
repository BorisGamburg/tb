from ipc.zmq_client import ZmqClient


class Orchestrator:
    def __init__(self, endpoint: str):
        self.client = ZmqClient(endpoint)

    def send_command(self, command: dict, timeout: float) -> dict:
        return self.client.request(command, timeout)

    def close(self):
        self.client.close()
