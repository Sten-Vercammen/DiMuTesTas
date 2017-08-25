# generic imports
import pickle
import threading
import logging

import datetime # to create unique timestamp
import os       # to get process id
import socket   # to get local ip
import time	# to wait before trying to reconnect


# specific imports
import pika

LOG_FORMAT = ('%(levelname) -10s %(asctime)s %(name) -30s %(funcName) '
              '-35s %(lineno) -5d: %(message)s')
LOGGER = logging.getLogger(__name__)

logging.basicConfig(level=logging.INFO, format=LOG_FORMAT)


class FunctionRunner:
    """
    Stores external functions, so that they only need to be imported once.
    """
    def __init__(self):
        self.f_dict = dict()

    def __call__(self, md, oti):
        f_name = md + "::" + oti
        exec_f = self.f_dict.get(f_name)
        if exec_f is None:
            exec_f = getattr(__import__(md, fromlist=[oti]), oti)
            self.f_dict[f_name] = exec_f
        return exec_f


class MsgBuilder:
    MSG_TYPE = 'MSG_TYPE'

    class MSG_TYPES:
        TASK = 'TASK'
        RESULT = 'RESULT'
        TASK_DONE = 'TASK_DONE'
        TASK_NEW = 'TASK_NEW'

    class MSG_PARAMS:
        WORK_QUEUE = 'WORK_QUEUE'
        COLLECT_QUEUE = 'COLLECT_QUEUE'

    class PARAMS_TASK:
        TASKS = 'TASKS'
        PARAMS = 'PARAMS'
        MSG_ID = 'MSG_ID'

    class _METHOD:
        MD = 'MD'
        OTI = 'OTI'

    class PARAMS_TASKS(_METHOD):
        MODIFIER = 'MODIFIER'

    class PARAMS_TASK_DONE(_METHOD):
        MSG_IDS = 'MSG_IDS'

    class PARAMS_TASK_NEW(PARAMS_TASK_DONE):
        pass

    class PARAMS_RESULT:
        RESULT = 'RESULT'
        EXCEPTION = 'EXCEPTION'

    @staticmethod
    def task_part(md, oti, modifier):
        if not isinstance(md, str) or not isinstance(oti, str):
            raise TypeError("Tasks must refer the name of the module and method")
        try:
            eval(modifier)
        except TypeError:
            raise TypeError("modifier must be callable (and in string format)")

        task = {MsgBuilder.PARAMS_TASKS.MD:  md,
                MsgBuilder.PARAMS_TASKS.OTI: oti}
        if modifier is not None:
            task.update({MsgBuilder.PARAMS_TASKS.MODIFIER: modifier})
        return task

    @staticmethod
    def task(tasks, params, work_queue, collect_queue, msg_id):
        if isinstance(tasks, list):
            if len(tasks) is 0:
                raise ValueError("Must have at least one task")
            for t in tasks:
                if not isinstance(t, dict):
                    raise TypeError("A task must be a dictionary")
        else:
            raise TypeError("Tasks must be a list")
        if not isinstance(work_queue, str) or not isinstance(collect_queue, str):
            raise TypeError("Queues must be referred by name")
        if not isinstance(msg_id, str):
            raise TypeError("msg id must be a string")

        msg = {MsgBuilder.MSG_TYPE:                 MsgBuilder.MSG_TYPES.TASK,
               MsgBuilder.PARAMS_TASK.TASKS:        tasks,
               MsgBuilder.PARAMS_TASK.PARAMS:       params,
               MsgBuilder.PARAMS_TASK.MSG_ID:       msg_id,
               MsgBuilder.MSG_PARAMS.WORK_QUEUE:    work_queue,
               MsgBuilder.MSG_PARAMS.COLLECT_QUEUE: collect_queue}
        return pickle.dumps(msg)

    @staticmethod
    def result(result, collect_queue, exception=None):
        if not isinstance(collect_queue, str):
            raise TypeError("Queue must be referred by name")

        msg = {MsgBuilder.MSG_TYPE:                 MsgBuilder.MSG_TYPES.RESULT,
               MsgBuilder.PARAMS_RESULT.RESULT:     result,
               MsgBuilder.MSG_PARAMS.COLLECT_QUEUE: collect_queue}
        # an exception can literally be None, so we need to check its type
        if isinstance(exception, Exception):
            msg.update({MsgBuilder.PARAMS_RESULT.EXCEPTION: exception})
        return pickle.dumps(msg)

    @staticmethod
    def task_done(collect_queue, md, oti, msg_ids):
        if not isinstance(collect_queue, str):
            raise TypeError("Queue must be referred by name")
        if not isinstance(md, str) or not isinstance(oti, str):
            raise TypeError("Tasks must refer the name of the module and method")
        if not isinstance(msg_ids, list) or len(msg_ids) == 0:
            raise TypeError("msg_ids must be a list of (at least 1) msg ids")
        for msg_id in msg_ids:
            if not isinstance(msg_id, str):
                raise TypeError("msg_id must be a string")

        msg = {MsgBuilder.MSG_TYPE:                 MsgBuilder.MSG_TYPES.TASK_DONE,
               MsgBuilder.PARAMS_TASK_DONE.MD:      md,
               MsgBuilder.PARAMS_TASK_DONE.OTI:     oti,
               MsgBuilder.PARAMS_TASK_DONE.MSG_IDS: msg_ids,
               MsgBuilder.MSG_PARAMS.COLLECT_QUEUE: collect_queue}
        return pickle.dumps(msg)

    @staticmethod
    def task_new(collect_queue, md, oti, msg_ids):
        if not isinstance(collect_queue, str):
            raise TypeError("Queue must be referred by name")
        if not isinstance(md, str) or not isinstance(oti, str):
            raise TypeError("Tasks must refer the name of the module and method")
        if not isinstance(msg_ids, list) or len(msg_ids) == 0:
            raise TypeError("msg_ids must be a list of (at least 1) msg ids")
        for msg_id in msg_ids:
            if not isinstance(msg_id, str):
                raise TypeError("msg_id must be a string")

        msg = {MsgBuilder.MSG_TYPE:                 MsgBuilder.MSG_TYPES.TASK_NEW,
               MsgBuilder.PARAMS_TASK_NEW.MD:       md,
               MsgBuilder.PARAMS_TASK_NEW.OTI:      oti,
               MsgBuilder.PARAMS_TASK_NEW.MSG_IDS:  msg_ids,
               MsgBuilder.MSG_PARAMS.COLLECT_QUEUE: collect_queue}
        return pickle.dumps(msg)


class TaskBuilder:
    def __init__(self, rti, work_queue='work_queue'):
        """
        Builds structure of tasks.
        :param rti: Remote Task Invocation middleware object
        :param work_queue: Name of the work_queue where the task resile

        :type rti: RTI
        :type work_queue: str
        """
        if not isinstance(rti, RTI):
            raise TypeError("Must provide RTI object")
        if not isinstance(work_queue, str):
            raise TypeError("Queue must be referred by name")

        self._RTI = rti
        self._work_queue = work_queue
        self._tasks = []
        self._collect = "result_of_" + self._work_queue + str(id(self))

    def __del__(self):
        # remove result queue when we the program leaves the scope of the TaskBuilder
        self._RTI.get_consumer_channel(self._collect).queue_delete(queue=self._collect)

    def _add_task_function(self, module_name, function_name, modifier):
        """
        Add task function to task list, this will determine the execution order of the task functions.

        :param module_name: the module in which the function can be found
        :param function_name: the function we want to make into a task
        :param modifier: a function that allows modifying the results to glue functions together
        """
        task = MsgBuilder().task_part(module_name, function_name, modifier)
        self._tasks.append(task)

    def add_task_1_1(self, module_name, function_name, modifier=None):
        """
        Add a task function with a singe return value.
        If your task should produce multiple return values (to create multiple other tasks) use add_task_1_N
        Order sensitive, as this will determine the execution order of the task functions.

        :param module_name: the module in which the function can be found
        :param function_name: the function we want to make into a task
        :param modifier: a function that allows modifying the results to glue functions together
        :return: self
        """
        if modifier is None:
            self._add_task_function(module_name, function_name, "(lambda x: [x])")
        else:
            self._add_task_function(module_name, function_name, "(lambda x: [" + modifier + "(x)])")
        return self

    def add_task_1_N(self, module_name, function_name, modifier=None):
        """
        Add a task function with multiple return values.
        Your task should produce multiple return values to create multiple other tasks (or results).
        Order sensitive, as this will determine the execution order of the task functions.

        :param module_name: the module in which the function can be found
        :param function_name: the function we want to make into a task
        :param modifier: a function that allows modifying the results to glue functions together
        :return: self
        """
        if modifier is None:
            self._add_task_function(module_name, function_name, "(lambda x: x)")
        else:
            self._add_task_function(module_name, function_name, "(lambda x: modifier(x))")
        return self

    def send_task(self, params=None):
        """
        Create a task that needs to be processed. The parameters should be given as a dictionary.

        :param params: the parameters of the first task function that will be executed.
        """
        if len(self._tasks) is 0:
            raise ValueError("Must have at least one task")
        if params is None:
            params = {}

        msg_ids = [self._RTI._send_task(queue=self._work_queue, params=params,
                                        tasks=self._tasks, collect=self._collect)]
        next_md = self._tasks[0].get(MsgBuilder.PARAMS_TASKS.MD)
        next_oti = self._tasks[0].get(MsgBuilder.PARAMS_TASKS.OTI)
        self._RTI._send_task_new(self._collect, next_md, next_oti, msg_ids)

    def process_results(self, result_func, excep_func=None):
        """
        Process the results of the final task function with the given result function.

        :param result_func: the function to be called for each result of the final task function,
        with its result as arguments
        :return: the result of the provided result function
        """
        if not callable(result_func):
            raise TypeError("result function must be callable")

        if callable(excep_func):
            self._RTI._excep_fun = excep_func

        self._RTI._result_func = result_func
        return self._RTI._process_results(queue=self._collect)


class ChannelSetup(object):
    """
    Class providing basic setup for a channel to communicate with a specific queue on the RabbitMQ server.
    """
    def __init__(self, queue_name, connection_parameters):
        """
        Store variables to connect with a queue on the RabbitMQ server.

        :param queue_name: the name of the queue to connect with
        :param connection_parameters: the connection parameter to authenticate with the RabbitMQ server
        """
        # user configurable parameters for the RabbitMQ connection
        self._queue_name = queue_name
        self._connection_parameters = connection_parameters
        # default parameters for the RabbitMQ connection
        self._connection = None
        self._channel = None
        self._closing = False

    def _connect(self):
        """
        Connect to RabbitMQ, returning the connection handle.
        When the connection is established, the _on_connection_open method will be invoked by pika

        :return: the created asynchronous pika.SelectConnection

        :rtype: pika.SelectConnection
        """
        LOGGER.debug('Connecting to host')
        return pika.SelectConnection(self._connection_parameters,
                                     on_open_callback=self._on_connection_open,
                                     on_open_error_callback=self._on_connection_error,
                                     on_close_callback=self._on_connection_closed,
                                     stop_ioloop_on_close=False)

    def _on_connection_open(self, unused_connection):
        """
        Method called by pika when the connection to RabbitMQ has been established

        :param unused_connection: unused connection provided by the pika api
        """
        LOGGER.debug('Connection opened')
        # open the channel
        self._open_channel()

    def _on_connection_error(self, unused_connection, error_message=None):
        """
        Method called by pika when the connection to RabbitMQ was not established due to an error.
        As we want to connect, we try to _reconnect.

        :param unused_connection: unused connection provided by the pika api
        :param error_message: The server provided error message if given
        """
        self._channel = None
        # if we are closing the connection, do not intervene, otherwise, _reconnect
        #LOGGER.warning('Connection error, reopening in 5 seconds: (%s)',
        #               error_message)
        if self._closing:
            self._connection.ioloop.stop()
        else:
            time.sleep(1)
            if self._connection != None:
                self._reconnect()
            else:
                self.run()

    def _on_connection_closed(self, connection, reply_code, reply_text):
        """
        Method invoked by pika when the connection to RabbitMQ is closed unexpectedly.
        As is is unexpected, we try to _reconnect.

        :param connection: The closed connection obj
        :param reply_code: The server provided reply_code if given
        :param reply_text: The server provided reply_text if given
        """
        self._channel = None
        # if we are closing the connection, do not intervene, otherwise, _reconnect
        if self._closing:
            self._connection.ioloop.stop()
        else:
            LOGGER.warning('Connection closed, reopening in 5 seconds: (%s) %s',
                           reply_code, reply_text)
            self._connection.add_timeout(5, self._reconnect)

    def _reconnect(self):
        """
        Reconnect to RabbitMQ.
        """
        # stop the old IOLoop
        self._connection.ioloop.stop()

        if not self._closing:
            self.run()

    def _open_channel(self):
        """
        Open a new channel to RabbitMQ
        """
        LOGGER.debug('Creating a new channel')
        self._connection.channel(on_open_callback=self._on_channel_open)

    def _on_channel_open(self, channel):
        """
        Method invoked by pika when the channel to RabbitMQ is opened

        :param channel: the opened channel
        """
        LOGGER.debug('Channel opened')
        # save channel
        self._channel = channel
        # add function to be executed when the channel closes
        LOGGER.debug('Adding channel close callback')
        self._channel.add_on_close_callback(self._on_channel_closed)
        # make sure the recipient queue exists,
        # by creating the queue on the RabbitMQ server (skipped if exists)
        self._setup_queue()

    def _on_channel_closed(self, channel, reply_code, reply_text):
        """
        Method invoked by pika when the channel to RabbitMQ is closed unexpectedly.
        Main reasons are violations of the protocol,
        like re-declaring an exchange or queue with different parameter.
        We thus close the connection to shutdown the object

        :param channel: The closed channel obj
        :param reply_code: The server provided reply_code if given
        :param reply_text: The server provided reply_text if given
        """
        LOGGER.warning('Channel %i was closed: (%s) %s',
                       channel, reply_code, reply_text)
        self._close_connection()

    def _setup_queue(self):
        """
        Setup the queue on the RabbitMQ server. If the queue exists, the creation is skipped.
        """
        LOGGER.debug('Declaring queue %s', self._queue_name)
        self._channel.queue_declare(queue=self._queue_name)

    def _close_channel(self):
        """
        Call to close the channel to the RabbitMQ server cleanly.
        """
        if self._channel:
            LOGGER.debug('Closing the channel')
            self._channel.close()
        else:
            LOGGER.debug('No channel to close')

    def _close_connection(self):
        """
        CLose the connection to the RabbitMQ server.
        """
        LOGGER.debug('Closing connection')
        self._connection.close()

    def run(self):
        """
        Connect to the RabbitMQ server and start the IOloop.
        """
        # create new connection
        self._connection = self._connect()
        # start new IOLoop on the new connection
        self._connection.ioloop.start()


class ConsumerChannel(ChannelSetup):
    def __init__(self, queue_name, connection_parameters):
        super(ConsumerChannel, self).__init__(queue_name, connection_parameters)
        self._callback = None

    def _setup_queue(self):
        """
        Setup the queue on the RabbitMQ server. If the queue exists, the creation is skipped.
        """
        # override to add function to be executed on acknowledgment of queue declaration
        LOGGER.debug('Declaring queue %s', self._queue_name)
        self._channel.queue_declare(self._on_queue_declareok, self._queue_name)

    def _on_queue_declareok(self, method_frame):
        """
        Method invoked by pika when the queue is declared.

        :param method_frame: the Queue.DeclareOk frame
        """
        LOGGER.debug('Queue declared')
        self._start_consuming()

    def _start_consuming(self):
        """
        Start consuming messages.
        But first add a cancel callback so that this object is notified when the RabbitMQ server cancels the consumer.
        """
        LOGGER.debug('Start consuming')
        # add method to execute when consumer is canceled
        LOGGER.debug('Adding consumer cancellation callback')
        self._channel.add_on_cancel_callback(self._on_consumer_cancelled)
        # only allow x messages to be pre-fetched per consumer!
        # this way, a consumer only receives a new messages
        # once it has sent the ack from the previous one.
        # Making the consumers work 'constantly' and with a fair dispatch.
        self._channel.basic_qos(prefetch_count=1)
        # save consumer tag + tell which function to execute when receiving a msg
        self._consumer_tag = self._channel.basic_consume(self._on_message,
                                                         self._queue_name)

    def _on_consumer_cancelled(self, method_frame):
        """
        Method invoked by pika when RabbitMQ sends a Basic.Cancel to a consumer.

        :param method_frame: The Basic.Cancel frame
        """
        # close channel
        LOGGER.debug('Consumer was cancelled remotely, shutting down: %r',
                    method_frame)
        self._close_channel()

    def _ack_msg_after_processing(f):
        """
        Use as function decorator to automatically send an ack of the message one you finish processing it.

        :return: wrapper function that automates sending the ack
        """
        def ack_msg_after_processing(self, unused_channel, basic_deliver, properties, body):
            r_func = None
            try:
                # save return function, this allows us to execute a function after sending the ack.
                # (usefull for stopping the consumer after acknowledging the last message)
                r_func = f(self, unused_channel, basic_deliver, properties, body)
            finally:
                # sent ack, so that the RabbitMQ server can delete it from its queue,
                # when no ack is send, the channel dies and there are other consumers,
                # the RabbitMQ server will redeliver the task to another consumer.
                # Therefore, no message will be lost (unless the RabbitMQ server dies).
                if self._channel:
                    LOGGER.debug('Acknowledging message %s', basic_deliver.delivery_tag)
                    self._channel.basic_ack(basic_deliver.delivery_tag)
                if callable(r_func):
                    r_func()
        return ack_msg_after_processing

    def _on_message(self, unused_channel, basic_deliver, properties, body):
        """
        Method invoked by pika when it receives a message from RabbitMQ

        :param unused_channel: the channel object
        :param basic_deliver: the basic_deliver method
        :param properties: the message properties
        :param body: the message itself
        """
        # pika 0.10.0: this need to run in a thread, otherwise heartbeats will not come through,
        # and the message we are processing on this worker (unacked on the server) will be be put back onto the server,
        # ready to be processed by another worker. This long-running worker (which is still processing the message)
        # will be unable to finish processing the message, but will not crash, and might not reconnect.
        # To prevent all this, we use an evil thread. Note: the unused_channel object is NOT thread safe!!!
        # (But as we only allow one message to be fetched and processed on the worker, this should be fine.)
        LOGGER.debug('Received message # %s from %s',
                    basic_deliver.delivery_tag, properties.app_id)
        threading.Thread(target=self._thread_func, args=(unused_channel, basic_deliver, properties, body)).start()

    @_ack_msg_after_processing
    def _thread_func(self, unused_channel, basic_deliver, properties, body):
        return self._callback(unused_channel, basic_deliver, properties, body)

    def _stop_consuming(self):
        """
        Tells RabbitMQ that you would like to stop consuming by sending Basic.Cancel
        """
        if self._channel:
            LOGGER.debug('Stop consuming')
            self._channel.basic_cancel(self._on_cancelok, self._consumer_tag)
        else:
            LOGGER.debug('No channel to stop consuming')

    def _on_cancelok(self, unused_frame):
        """
        Method invoked by pika when RabbitMQ acknowledges the cancellation of a consumer.

        :param unused_frame: The Basic.CancelOk frame
        """
        # close channel
        LOGGER.debug('RabbitMQ acknowledged the cancellation of the consumer')
        self._close_channel()

    def stop(self):
        """
        Cleanly shutdown the consumer by closing the channel and consequently the connection.
        """
        LOGGER.debug('Stopping')
        self._closing = True
        self._stop_consuming()
        # Connection is restarted for pika to communicate with RabbitMQ
        self._connection.ioloop.start()
        LOGGER.debug('Stopped')


class ProducerChannel(ChannelSetup):
    """
    Class providing interface to produce messages onto a specific queue on the RabbitMQ server.
    """
    def __init__(self, queue_name, connection_parameters, exchange_name=''):
        """
        Store variables to connect with a queue on the RabbitMQ server.

        :param queue_name: the name of the queue to connect with
        :param connection_parameters: the connection parameter to authenticate with the RabbitMQ server
        :param exchange_name: the name of the exchange used to route messages to the queue on the RabbitMQ server
        """
        super(ProducerChannel, self).__init__(queue_name, connection_parameters)
        self._exchange_name = exchange_name
        self._exchange_type = 'direct'

        # save send messages until they are acknowledged
        self._deliveries = dict()

        # needed to block sending messages as this is NOT thread safe
        self._mutex = threading.RLock()

        # variables to keep some statistics
        self._acked = 0
        self._nacked = 0
        self._message_number = 0

    def _setup_queue(self):
        """
        Setup the queue on the RabbitMQ server. If the queue exists, the creation is skipped.
        """
        # override to add function to be executed on acknowledgment of queue declaration
        LOGGER.debug('Declaring queue %s', self._queue_name)
        self._channel.queue_declare(self._on_queue_declareok, self._queue_name)

    def _on_queue_declareok(self, method_frame):
        """
        Method invoked by pika when the queue is declared.

        :param method_frame: the Queue.DeclareOk frame
        """
        LOGGER.debug('Queue declared')
        self._enable_delivery_confirmations()

    def _enable_delivery_confirmations(self):
        """
        Enable delivery confirmations. The only way to turn this off is to close the channel and create a new one.
        """
        self._channel.confirm_delivery(self._on_delivery_confirmation)

    def _on_delivery_confirmation(self, method_frame):
        """
        Method invoked by pika when the RabbitMQ server responds to a Basic.Publish command.
        It either is a ack or a nack of the published message.
        In the case of a nack, we republish the message.

        :param method_frame: Basic.Ack or Basic.Nack frame
        """
        # get confirmation type
        confirmation_type = method_frame.method.NAME.split('.')[1].lower()
        # acquire mutex as sending messages and or changing a dictionary isn' thread safe
        self._mutex.acquire()
        try:
            if confirmation_type == 'ack':
                # remove delivered message
                self._acked += 1
                del self._deliveries[method_frame.method.delivery_tag]
            elif confirmation_type == 'nack':
                # republish message
                self._nacked += 1
                msg = self._deliveries.pop(method_frame.method.delivery_tag)
                if msg is not None:
                    self.publish_message(msg)
                else:
                    raise ValueError('nack message does not exist anymore')
        finally:
            self._mutex.release()

    def publish_message(self, msg):
        """
        Publish the provided message. The message will be send to the queue provided at initialization.

        :param msg: the message we want to publish
        """
        if self._channel is None or not self._channel.is_open:
            # cannot send message if channel doesn't exists or isn't open
            LOGGER.debug('Channel is None or not open')
            return
        # acquire mutex as sending messages isn' thread safe
        self._mutex.acquire()
        try:
            LOGGER.debug('publish msg')
            self._channel.basic_publish(exchange=self._exchange_name,
                                        routing_key=self._queue_name,
                                        body=msg)

            self._message_number += 1
            # wave published message until we receive it's ack
            self._deliveries[self._message_number] = msg
        finally:
            self._mutex.release()

    def _run(self):
        # create new connection
        self._connection = self._connect()
        # start new IOLoop on the new connection
        self._connection.ioloop.start()

    def run(self):
        """
        Connect to the RabbitMQ server and start the IOloop.
        """
        t = threading.Thread(target=self._run)
        # set as daemon, so that this does not keep the python script alive when the main thread exits
        t.daemon=True
        t.start()

    def stop(self):
        """
        Cleanly shutdown the producer by closing the channel and consequently the connection.
        """
        self._closing = True
        self._close_channel()
        LOGGER.debug('Stopped')


class ConnectionParams(object):
    """
    Class that only saves the connection parameters. It existence is needed to allow ConsumerChannels and
    ProducerChannels to exist alone and in no particular order as base classes for the RTI.
    As we use co-operative subclassing, which need consistent initializer parameters.
    """
    def __init__(self, connection_parameters):
        super(ConnectionParams, self).__init__()
        self._connection_parameters = connection_parameters


class ConsumerChannels(ConnectionParams):
    """
    Class saving the unique channel and connection for each consumer to a single queue.
    """
    def __init__(self, connection_parameters):
        super(ConsumerChannels, self).__init__(connection_parameters)
        self._consumer_channels = dict()

    def get_consumer_channel(self, queue_name):
        """
        Returns the unique ConsumerChannel specific to the specified queue.
        If there is no consumer channel, one will be created.

        :param queue_name: the name of the queue which we want to get a consumer channel for
        :return: ConsumerChannel
        """
        # get dedicated channel for queue
        channel = self._consumer_channels.get(queue_name)
        if channel is None:
            # no channel is setup for specific queue, create anew ------------|
            channel = ConsumerChannel(queue_name, self._connection_parameters)
            # save dedicated channel for queue
            self._consumer_channels[queue_name] = channel
        return channel


class ProducerChannels(ConnectionParams):
    def __init__(self, connection_parameters):
        super(ProducerChannels, self).__init__(connection_parameters)
        self._producer_channels = dict()

    def get_producer_channel(self, queue_name):
        """
        Returns the unique ProducerChannel specific to the specified queue.
        If there is no producer channel, one will be created.

        :param queue_name: the name of the queue which we want to get a producer channel for
        :return: ProducerChannel
        """
        # get dedicated channel for queue
        channel = self._producer_channels.get(queue_name)
        if channel is None:
            # no channel is setup for specific queue, create anew ------------|
            channel = ProducerChannel(queue_name, self._connection_parameters)
            # save dedicated channel for queue
            self._producer_channels[queue_name] = channel
            # run channel
            channel.run()
            # as a producer channel needs some time to setup before we can start sending messages,
            # we will block until it is set up
            import time
            # wait until channel exists
            while channel._channel is None:
                time.sleep(1)
        return channel


class RTI(ProducerChannels, ConsumerChannels):
    """
    Remote Task Invocation middleware. This object allows us to schedule tasks on remote machines and/or
    execute those tasks on the remote machines their end.
    """
    def __init__(self, user, password, host):
        # set credentials to authenticate connection
        credentials = pika.PlainCredentials(user,
                                            password)

        # set parameters to authenticate to RabbitMQ server
        connection_parameters = pika.ConnectionParameters(host=host,
                                                          credentials=credentials)

        super(RTI, self).__init__(connection_parameters)

        # a place to store the external functions
        self._external_funcs = FunctionRunner()

        # saves the progress of all the tasks (used to determine when all tasks are done processing)
        self._tasks_progress = dict()

        # saves the function to be called 
        self._result_func = None

        # saves the exception function to be called
        self._excep_func = None

        # save local ip into msg_id
        self._msg_id = [l for l in ([ip for ip in socket.gethostbyname_ex(socket.gethostname())[2] if not ip.startswith("127.")][:1], [[(s.connect(('8.8.8.8', 53)), s.getsockname()[0], s.close()) for s in [socket.socket(socket.AF_INET, socket.SOCK_DGRAM)]][0][1]]) if l][0][0]
        # add own process id
        self._msg_id += "::" + str(os.getpid()) + "::"

        # store last timestamp
        self._last_timestamp = ""

    def _get_unique_msg_id(self):
        # make sure we have a unique msd_id
        # local ip, own process id and unique timestamp (within process)
        while True:
            msg_timestamp = str(datetime.datetime.utcnow())
            if msg_timestamp != self._last_timestamp:
                self._last_timestamp = msg_timestamp
                return self._msg_id + msg_timestamp

    def _send_task(self, queue, params, tasks, collect):
        # encode arguments as str message (encode expects a dictionary)
        msg_id = self._get_unique_msg_id()
        msg = MsgBuilder.task(tasks, params, queue, collect, msg_id)
        self.get_producer_channel(queue).publish_message(msg)
        return msg_id

    def _send_result(self, queue, result, exception=None):
        # encode as str message (encode expects a dictionary)
        msg = MsgBuilder.result(result, queue, exception)
        self.get_producer_channel(queue).publish_message(msg)

    def _send_task_done(self, queue, md, oti, msg_ids):
        # encode as str message (encode expects a dictionary)
        msg = MsgBuilder.task_done(queue, md, oti, msg_ids)
        self.get_producer_channel(queue).publish_message(msg)

    def _send_task_new(self, queue, md, oti, msg_ids):
        # encode as str message (encode expects a dictionary)
        msg = MsgBuilder.task_new(queue, md, oti, msg_ids)
        self.get_producer_channel(queue).publish_message(msg)

    def _process(self, queue, callback,):
        channel = self.get_consumer_channel(queue)
        channel._callback = callback
        channel.run()

    def process_tasks(self, queue='work_queue'):
        self._process(queue, self._callback_task)

    def _process_results(self, queue):
        self._process(queue, self._callback_result)

    def _callback_task(self, ch, method, properties, body):
        # convert to utf-8 dict ----------------------------------------------|
        msg_dict = pickle.loads(body)
        # check msg_type -------------------------------------------------|
        if msg_dict.get(MsgBuilder.MSG_TYPE) != MsgBuilder.MSG_TYPES.TASK:
            print "Error: received msg (" + msg_dict.get(MsgBuilder.MSG_TYPE) + ") which isn't a " + MsgBuilder.MSG_TYPES.TASK
            return
        # extract params -----------------------------------------------------|
        # msg parameters
        work_queue = msg_dict.get(MsgBuilder.MSG_PARAMS.WORK_QUEUE)
        collect_queue = msg_dict.get(MsgBuilder.MSG_PARAMS.COLLECT_QUEUE)
        tasks = msg_dict.get(MsgBuilder.PARAMS_TASK.TASKS)
        msg_id = msg_dict.get(MsgBuilder.PARAMS_TASK.MSG_ID)
        # task and parameters
        task = tasks.pop(0)
        params = msg_dict.get(MsgBuilder.PARAMS_TASK.PARAMS)
        # task function
        md = task.get(MsgBuilder.PARAMS_TASKS.MD)
        oti = task.get(MsgBuilder.PARAMS_TASKS.OTI)
        # result modifier
        modifier = task.get(MsgBuilder.PARAMS_TASKS.MODIFIER)
        try:
            # execute task -------------------------------------------------------|
            # get external function
            exec_function = self._external_funcs(md, oti)
            # execute external function
            if params is None:
                result = exec_function()
            elif isinstance(params, list) or isinstance(params, tuple):
                result = exec_function(*params)
            elif isinstance(params, dict):
                result = exec_function(**params)
            else:
                result = exec_function(params)
        except Exception as e:
            self._send_result(collect_queue, None, e)
        else:
            # execute modifier on result -----------------------------------------|
            # allows for splitting result into multiple tasks
            # (for 1:1, modifier returns [result],
            # for 1:N, result is iterable, and return result
            result = eval(modifier)(result)
            # send back return value ---------------------------------------------|
            if len(tasks) is 0:
                # this is the last step, send results to collect queue
                try:
                    for r in result:
                        self._send_result(collect_queue, r)
                except TypeError:
                    self._send_result(collect_queue, result)
            else:
                next_task = tasks[0]
                next_md = next_task.get(MsgBuilder.PARAMS_TASKS.MD)
                next_oti = next_task.get(MsgBuilder.PARAMS_TASKS.OTI)
                try:
                    if len(result) > 0: # if the user want to return [], he needed to return [[]], or used the modifier function
                        next_msg_ids = []
                        for r in result:
                            next_msg_ids.append(self._send_task(work_queue, r, tasks, collect_queue))
                        self._send_task_new(collect_queue, next_md, next_oti, next_msg_ids)
                except TypeError:
                    next_msg_ids = [self._send_task(work_queue, result, tasks, collect_queue)]
                    self._send_task_new(collect_queue, next_md, next_oti, next_msg_ids)
        finally:
            # send back statistics (needed to end get_results function)
            self._send_task_done(collect_queue, md, oti, [msg_id])

    def _callback_result(self, ch, method, properties, body):
        # convert to utf-8 dict ----------------------------------------------|
        msg_dict = pickle.loads(body)
        # check msg_type -----------------------------------------------------|
        msg_type = msg_dict.get(MsgBuilder.MSG_TYPE)
        if msg_type == MsgBuilder.MSG_TYPES.RESULT:
            self._process_result(msg_dict)
        elif msg_type == MsgBuilder.MSG_TYPES.TASK_DONE:
            self._process_task_done(msg_dict)
        elif msg_type == MsgBuilder.MSG_TYPES.TASK_NEW:
            self._process_task_new(msg_dict)
        else:
            print "Error: received unknown msg type: " + msg_type
            return
        # check if we are done consuming -------------------------------------|
        result_queue = msg_dict.get(MsgBuilder.MSG_PARAMS.COLLECT_QUEUE)
        if self._received_all(result_queue):
            # small hack to execute this after we send the ack
            return lambda: self.get_consumer_channel(result_queue).stop()

    def _process_result(self, msg_dict):
        # extract params -----------------------------------------------------|
        result_params = msg_dict.get(MsgBuilder.PARAMS_RESULT.RESULT)
        # if an exception occurred, we do not have a result, handle the exception
        if MsgBuilder.PARAMS_RESULT.EXCEPTION in msg_dict:  # an exception can literally be None
            exception = msg_dict.get(MsgBuilder.PARAMS_RESULT.EXCEPTION)
            if self._excep_func is None:
                # exception occurred, user did not provide exception handling function,
                # -> raise the exception as an exception
                raise exception
            else:
                # exception occurred, user provides exception handling function
                # -> process the exception
                self._excep_func(exception)
        else:
            # execute result function
            if result_params is None:
                self._result_func()
            elif isinstance(result_params, list) or isinstance(result_params, tuple):
                self._result_func(*result_params)
            elif isinstance(result_params, dict):
                self._result_func(**result_params)
            else:
                self._result_func(result_params)

    def _process_task_done(self, msg_dict):
        # extract params -----------------------------------------------------|
        collect_queue = msg_dict.get(MsgBuilder.MSG_PARAMS.COLLECT_QUEUE)
        md = msg_dict.get(MsgBuilder.PARAMS_TASK_DONE.MD)
        oti = msg_dict.get(MsgBuilder.PARAMS_TASK_DONE.OTI)
        msg_ids = msg_dict.get(MsgBuilder.PARAMS_TASK_DONE.MSG_IDS)
        # remove the ids of the processed tasks ------------------------------|
        queue_statistics = self._tasks_progress.get(collect_queue, dict())
        task_name = md + "::" + oti
        to_process_msgs = queue_statistics.get(task_name, set())
        LOGGER.debug("remove ids: " + str(msg_ids))
        for msg_id in msg_ids:
            to_process_msgs.discard(msg_id)
        queue_statistics[task_name] = to_process_msgs
        self._tasks_progress[collect_queue] = queue_statistics

    def _process_task_new(self, msg_dict):
        # extract params -----------------------------------------------------|
        collect_queue = msg_dict.get(MsgBuilder.MSG_PARAMS.COLLECT_QUEUE)
        md = msg_dict.get(MsgBuilder.PARAMS_TASK_NEW.MD)
        oti = msg_dict.get(MsgBuilder.PARAMS_TASK_NEW.OTI)
        msg_ids = msg_dict.get(MsgBuilder.PARAMS_TASK_NEW.MSG_IDS)
        # save the ids of the task we need to process-------------------------|
        queue_statistics = self._tasks_progress.get(collect_queue, dict())
        task_name = md + "::" + oti
        to_process_msgs = queue_statistics.get(task_name, set())
        for msg_id in msg_ids:
            to_process_msgs.add(msg_id)
        queue_statistics[task_name] = to_process_msgs
        self._tasks_progress[collect_queue] = queue_statistics

    def _received_all(self, queue):
        LOGGER.debug('Checking received status')
        LOGGER.debug(str(self._tasks_progress.get(queue, dict())))
        for key, value in self._tasks_progress.get(queue, dict()).iteritems():
            LOGGER.debug(str(key) + ', ' + str(value))
            if len(value) > 0:
                return False
        LOGGER.debug('Received all')
        return True
