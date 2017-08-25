#!/bin/bash

cd ../master
docker build -t master .
cd ../worker
docker build -t worker .