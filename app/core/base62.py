BASE62_ALPHABET = "0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ"


def encode_base62(value: int) -> str:
    if value < 0:
        raise ValueError("Base62 value must be non-negative")
    if value == 0:
        return BASE62_ALPHABET[0]

    result = []
    base = len(BASE62_ALPHABET)
    while value:
        value, remainder = divmod(value, base)
        result.append(BASE62_ALPHABET[remainder])

    return "".join(reversed(result))
