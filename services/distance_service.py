def get_distance(
    price_a,
    price_b,
):

    return abs(
        price_a - price_b
    )


def is_min_distance_ok(
    price_a,
    price_b,
    required_distance,
):

    distance = get_distance(
        price_a,
        price_b,
    )

    return distance >= required_distance


def is_distance_ok(
    price,
    entries,
    required_distance,
):

    for entry in entries:

        ok = is_min_distance_ok(
            price_a=price,
            price_b=entry.price,
            required_distance=required_distance,
        )

        if not ok:
            return False

    return True