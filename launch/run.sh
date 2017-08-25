# change to how many workers you want per node ---------|
WORKERS_PER_NODE=1
# //////////////////////////////////////////////////////|
# change values acording to your used fileserver -------|
# \\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\|
# unless you use a Docker network plugin,
# the local driver will be used to attach the volumes
VOLUME_DRIVER='local'
# change to the fileserver type you use
VOLUME_TYPE='nfs4'
# change to the IP Address of your fileserver
ST_SRC='192.168.2.9'
# change to your exproted directory of your fileserver
ST_DEVICE='/home/ubuntu/data'
# //////////////////////////////////////////////////////|
# default parameters (no need to change below here) ----|
# \\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\|
# parameters to connect to the RabbitMQ server
USER_NAME='user'
PASSWORD='password'
# network related parameters
NETWORK_OVERLAY_HOST_NAME='multi-host-rabbitmq-nw'
LOCAL_SUBNET='172.20.9.0/24'
# docker container names
HOST_NAME_RABBIT='host-rabbit'
MASTER_NAME='master'
WORKER_NAME='worker'
# docker images names
DOCKER_NAME_RABBITMQ='rabbitmq:3-management'
DOCKER_NAME_MASTER='master'
DOCKER_NAME_WORKER='worker'
# mount location for fileserver's exported directory
ST_DST='/usr/local/data'
# //////////////////////////////////////////////////////|
# Docker lauch commands --------------------------------|
# \\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\|
# Lauch the RabbitMQ server
docker service create                           \
    `# container name `                         \
    --name $HOST_NAME_RABBIT                    \
    `# change default 'guest' user `            \
    -e RABBITMQ_DEFAULT_USER=$USER_NAME         \
    `# change default 'guest' password `        \
    -e RABBITMQ_DEFAULT_PASS=$PASSWORD          \
    `# connect to overlay network `             \
    --network $NETWORK_OVERLAY_HOST_NAME        \
    `# publish admin port on 15672`             \
    --publish 15672:15672                       \
    `# rabbitmq with browser management plugin` \
    $DOCKER_NAME_RABBITMQ
# Lauch the master (constraint to this node)
THIS_NODES_ID=$(docker node inspect -f {{.ID}} self)
docker service create                           \
    `# needed when using private docker repo`   \
    --with-registry-auth                        \
    `# container name`                          \
    --name $MASTER_NAME                         \
    `# constraint master to this node`          \
    --constraint "node.id == $THIS_NODES_ID"    \
    `# connect to overlay network`              \
    --network $NETWORK_OVERLAY_HOST_NAME        \
    `# do not restart even when failed`         \
    --restart-condition none                    \
    `# mount the fileserver`                    \
    --mount type=volume,src=$ST_SRC,dst=$ST_DST,volume-driver="$VOLUME_DRIVER",volume-opt="type=$VOLUME_TYPE",volume-opt="o=addr=$ST_SRC",volume-opt="device=:$ST_DEVICE" \
    `# customisable variables, see all in README.md`\
    -e BUILDCOMMAND=mvn,verify -e TIMEOUT=60    \
    `# the docker image of the producer`        \
    $DOCKER_NAME_MASTER
for (( i = 0; i < WORKERS_PER_NODE; i++ )); do
    # Lauch the workers
    docker service create                       \
        `# needed when using private docker repo`\
        --with-registry-auth                    \
        `# container name`                      \
        --name $WORKER_NAME$i                   \
        `# connect to overlay network`          \
        --network $NETWORK_OVERLAY_HOST_NAME    \
        `# launch one instance on each node`    \
        --mode global                           \
        `# only restart when failure occured`   \
        --restart-condition on-failure          \
        `# mount the fileserver`                \
        --mount type=volume,src=$ST_SRC,dst=$ST_DST,volume-driver="$VOLUME_DRIVER",volume-opt="type=$VOLUME_TYPE",volume-opt="o=addr=$ST_SRC",volume-opt="device=:$ST_DEVICE" \
        `# customisable variables, see all in README.md`\
        -e BUILDCOMMAND=mvn,verify -e TIMEOUT=60    \
        `# the docker image of the worker`      \
        $DOCKER_NAME_WORKER
done
# //////////////////////////////////////////////////////|
# Shutdown containers once master finishes -------------|
# \\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\|
# get ID of master container
MASTER_ID=$(docker service inspect -f {{.ID}} $DOCKER_NAME_MASTER)
# the only event fullfilling all filters is the correctly finising of the master 
while read -r line; do
    # remove our started services
    docker service rm $DOCKER_NAME_MASTER $HOST_NAME_RABBIT
    for (( i = 0; i < WORKERS_PER_NODE; i++ )); do
        # comment this line if you want to know the timings (see README.md)
        docker service rm $DOCKER_NAME_WORKER$i
    done
    break
done < <(docker events --filter 'event=die' --filter 'label=exitCode=0' --filter "label=com.docker.swarm.service.id=$MASTER_ID")
echo "done"
