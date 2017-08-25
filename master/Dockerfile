FROM ubuntu:latest

# install package dependancies
RUN apt-get update -y && apt-get install -y \
	ant \
	git \
	maven \
	openjdk-8-jdk \
	pypy \
	python-dev \
	python-pip \
	python-setuptools \
	virtualenv \
	&& rm -rf /var/lib/apt/lists/* # clean package cache to keep image size small

# copy files
COPY Makefile Makefile
# copy LittleDarwin setup file
COPY setupLittleDarwin.py /usr/local/
# copy taskit
COPY tasKIT /usr/local/tasKIT
# copy wrapper
COPY wrapper /usr/local/wrapper

# setup image
RUN make setup

COPY master.py /usr/local/master/
CMD ["make", "master", "-e", "SOURCE_PATH=$(SOURCEPATH)", "BUILD_PATH=$(BUILDPATH)", "BUILD_COMMAND=$(BUILDCOMMAND)", "TEST_PATH=$(TESTPATH)", "TEST_COMMAND=$(TESTCOMMAND)", "INITIAL_BUILD_COMMAND=$(INITIALBUILDCOMMAND)", "TIME_OUT=$(TIMEOUT)", "CLEAN_UP=$(CLEANUP)", "ALTERNATE_DB=$(ALTERNATEDB)"]
