import tasKIT
import MutatorWrapper

import logging
import TimeIt

import signal	# signal
import sys	# exit


def handler(signum, frame):
    print 'Signal handler called with signal', signal
    TimeIt.print_timings()
    sys.exit(0)

# Set the signal handler
signal.signal(signal.SIGINT, handler)
signal.signal(signal.SIGTERM, handler)

if __name__ == "__main__":

    LOG_FORMAT = ('%(levelname) -10s %(asctime)s %(name) -30s %(funcName) '
                  '-35s %(lineno) -5d: %(message)s')
    LOGGER = logging.getLogger(__name__)

    logging.basicConfig(level=logging.INFO, format=LOG_FORMAT)

    LOGGER.info("start initial build")
    # 1) initial build check to avoid false results. the system must be able to build cleanly without errors.
    MutatorWrapper.initial_build()

    LOGGER.info("setup RTI")
    RTI = tasKIT.RTI('user', 'password', 'host-rabbit')             # provide credentials for RabbitMQ

    LOGGER.info("setup taskbuilder")
    try:
        tb = (tasKIT.TaskBuilder(RTI, 'work_queue')                 # specify task queue on which workers listen
              .add_task_1_N('MutatorWrapper', 'generate_mutants')   # add module and function-name for the workers to execute
              .add_task_1_1('MutatorWrapper', 'process_mutant'))    # add module and function-name for the workers to execute

        LOGGER.info("send file names")
        for file_name in MutatorWrapper.get_file_names():           # get all the names of the files to mutate
            tb.send_task(file_name)                                 # queue the parameters for the function the workers execute
                                                                    # 2) which is sending the filenames to the queue

        tb.process_results(MutatorWrapper.process_result)           # gather results
        MutatorWrapper.generate_report()                            # generate report

    except Exception as e:
        print "excepton occured:\n"
        print e
    finally:
        LOGGER.info("done")
        TimeIt.print_timings()
