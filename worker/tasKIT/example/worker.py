import tasKIT

RTI = tasKIT.RTI('user', 'password', 'localhost')
work_queue = 'work_queue'


RTI.process_tasks(work_queue, 1)