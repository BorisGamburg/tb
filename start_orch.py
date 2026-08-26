from orchestrator.orchestrator import Orchestrator


if __name__ == "__main__":
    orchestrator = Orchestrator(
        "ipc:///tmp/CHILLGUYUSDT_hedge_2.sock"
    )

    result = orchestrator.send_command({
        "command": "TEST",
    })

    print(result)
    orchestrator.close()
