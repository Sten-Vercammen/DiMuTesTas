from contextlib import contextmanager
import time

timing_funcs = dict()
timing_contexts = dict()


def time_func(method):
    """
    Use as function decorator to store the execution time of the function.
    (Cumulative)
    The module and name of the method are used to differentiate the timing_funcs.
    e.g.:
    @time_func
    def f():
        statements
    """
    def timed(*args, **kwargs):
        ts = time.time()
        result = method(*args, **kwargs)
        te = time.time()

        timing_funcs[method] = timing_funcs.get(method, 0.0) + te - ts

        return result

    return timed


@contextmanager
def time_context(module, context):
    """
    Encapsulate code block in with statement to store its execution time.
    (Cumulative)
    The provided module and context are used to differentiate the timing_funcs.
    e.g.:
    with time_context(module, context):
        statements
    :param module:
    :param context:
    :return:
    """
    if not isinstance(module, str) or not isinstance(context, str):
        raise TypeError("module and context must be strings")
    ts = time.time()
    yield
    te = time.time()
    timing_contexts[(module, context)] = timing_contexts.get((module, context), 0.0) + te - ts


def print_timings():
    total = 0.0
    for method, runtime in timing_funcs.iteritems():
        print '%s::%s %.2f sec' % \
              (method.__module__, method.__name__, runtime)
        total += runtime
    for context, runtime in timing_contexts.iteritems():
        print '%s::%s %.2f sec' % \
              (context[0], context[1], runtime)
        total += runtime
    print 'total %.2f sec' % total
