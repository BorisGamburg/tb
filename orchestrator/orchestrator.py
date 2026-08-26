from ipc.zmq_client import ZmqClient


class Orchestrator:
    def __init__(self, endpoint: str):
        self.client = ZmqClient(endpoint)

    def send_command(self, command: dict) -> dict:
        return self.client.request(command)

    def close(self):
        self.client.close()
