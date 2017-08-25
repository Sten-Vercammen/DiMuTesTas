#!/bin/bash
echo 'creating overlay network on host'

# create the local bridged network with the given subnet
docker network create \
	--driver overlay \
	--subnet 172.20.9.0/24 \
	multi-host-rabbitmq-nw

echo 'done creating overlay network on host'
printf '_%.0s' {1..80}
echo ''
