"""V9.6 research-only trade accounting helpers.

Returns hypothetical outcomes in risk units; no orders or live feeds.
"""
def gross_r(first_target, second_target, initial_stop):
    if initial_stop:
        if first_target or second_target:
            raise ValueError("Contradictory exit flags")
        return -1.0
    if second_target and not first_target:
        raise ValueError("Second target requires first target")
    if second_target:
        return 1.5
    if first_target:
        return 0.5
    return None
