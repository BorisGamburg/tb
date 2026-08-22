from dataclasses import dataclass
import importlib


@dataclass(frozen=True)
class Account:
    api_key: str
    api_secret: str
    demo: bool


def load_account(account_name: str) -> Account:

    try:
        module = importlib.import_module(
            f"accounts.{account_name}"
        )

    except ModuleNotFoundError as e:
        raise RuntimeError(
            f"Unknown account: {account_name}"
        ) from e

    account = getattr(
        module,
        "ACCOUNT",
    )

    if not isinstance(account, Account):
        raise TypeError(
            f"{account_name}: invalid ACCOUNT object"
        )

    return account