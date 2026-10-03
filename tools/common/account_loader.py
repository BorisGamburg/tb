import importlib
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(PROJECT_ROOT))

from accounts.account import Account


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