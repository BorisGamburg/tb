from utils.utils import get_inverse_side


def is_position_limit_allowed(proxy_driver, symbol: str, side: str) -> bool:
    pyramid_position = proxy_driver.get_position(symbol, side)
    main_position = proxy_driver.get_position(
        symbol,
        get_inverse_side(side),
    )

    pyramid_qty = float(pyramid_position["size"])
    main_qty = float(main_position["size"])

    return pyramid_qty < main_qty * 0.5
