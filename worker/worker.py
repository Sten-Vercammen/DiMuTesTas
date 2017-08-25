#!/usr/bin/env python
"""
Worker, executing functions from installed modules.
"""

# specific imports
import tasKIT
import TimeIt

import logging

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

    try:
        RTI = tasKIT.RTI('user', 'password', 'host-rabbit')
        work_queue = 'work_queue'

        RTI.process_tasks(work_queue)
    except Exception as e:
        print "excepton occured:\n"
        print e
    finally:
        LOGGER.info("done")
        TimeIt.print_timings()
