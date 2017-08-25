# generic imports
import time

# specific imports
import tasKIT

RTI = tasKIT.RTI('user', 'password', 'localhost')
work_queue = 'work_queue'


# time-consuming task which we run remote,
# can return what it wants
def task1(x):
    time.sleep(10)
    return x + x

# time-consuming task which we run remote,
# can return what it wants
def task2(x):
    time.sleep(10)
    return 10*x



# global variables
total = 0
def reduce(x):
    global total
    total += x
    print x, total


if __name__ == "__main__":
    print total

    tb = tasKIT.TaskBuilder(RTI, work_queue) \
        .add_task_1_N('main', 'task1') \
        .add_task_1_1('main', 'task2')

    for x in xrange(0, 100):
        tb._send_task({'x': x})

    [reduce(x) for x in tb.get_results()]
    print total
