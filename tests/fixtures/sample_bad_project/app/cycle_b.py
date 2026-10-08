from app.cycle_a import helper_a


def helper_b():
    return 42


def uses_a():
    return helper_a()
