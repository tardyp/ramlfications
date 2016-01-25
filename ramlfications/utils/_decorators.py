from ramlfications.errors import BaseRAMLError


def collecterrors(func):
    def func_wrapper(inst, attr, value):
        if not inst.errors:
            inst.errors = []
        try:
            func(inst, attr, value)
        except BaseRAMLError as e:
            inst.errors.append(e)

    return func_wrapper
