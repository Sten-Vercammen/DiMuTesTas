SHELL:=/bin/bash

# Makefile for easy listing of commands

# the program where the mutator engine is located
MUTATOR_REPOSITORY		:= https://github.com/Sten-Vercammen/LittleDarwin.git
# specific commit or branch-name
SPECIFIC_MUTATOR_COMMIT	:= master

# actual execution command for master and workers: ------------------------|
#\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\|
# command to generate mutants
RUN_MASTER_CMD	= $(pypy) $(master_py) -m -p $(test_subject_dir)$(SOURCE_PATH) -t $(test_subject_dir)$(BUILD_PATH) -c $(BUILD_COMMAND)
# command to execute the mutants
RUN_WORKER_CMD	= $(pypy) $(worker_py) -b -p $(test_subject_dir)$(SOURCE_PATH) -t $(test_subject_dir)$(BUILD_PATH) -c $(BUILD_COMMAND)

#/////////////////////////////////////////////////////////////////////////////|
# default values for the above command
# it is best to change them with the -e command 
#\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\| 
# must set values
SOURCE_PATH			= src/main/
BUILD_PATH			= 
BUILD_COMMAND		= mvn,test

ifeq ($(subst $(space),,$(SOURCE_PATH)),)
	override SOURCE_PATH	= src/main/
endif
ifeq ($(subst $(space),,$(BUILD_COMMAND)),)
	override BUILD_COMMAND	= mvn,test
endif

# optional values, not defined when noting after = and when not overwriten with make -e
TEST_PATH				= 
TEST_COMMAND			= 
INITIAL_BUILD_COMMAND	= 
TIME_OUT				= 
CLEAN_UP				= 
ALTERNATE_DB			= 

space :=
space +=

ifdef TEST_PATH
	ifneq ($(subst $(space),,$(TEST_PATH)),)
		EXTRAFLAGS		+= --test-path $(test_subject_dir)$(TEST_PATH)
	endif
endif
ifdef TEST_COMMAND
	ifneq ($(subst $(space),,$(TEST_COMMAND)),)
		EXTRAFLAGS		+= --test-command $(TEST_COMMAND)
	endif
endif
ifdef INITIAL_BUILD_COMMAND
	ifneq ($(subst $(space),,$(INITIAL_BUILD_COMMAND)),)
		EXTRAFLAGS		+= --initial-build-command $(INITIAL_BUILD_COMMAND)
	endif
endif
ifdef TIME_OUT
	ifneq ($(subst $(space),,$(TIME_OUT)),)
		EXTRAFLAGS		+= --timeout $(TIME_OUT)
	endif
endif
ifdef CLEAN_UP
	ifneq ($(subst $(space),,$(CLEAN_UP)),)
		EXTRAFLAGS		+= --cleanup $(CLEAN_UP)
	endif
endif
ifdef ALTERNATE_DB
	ifneq ($(subst $(space),,$(ALTERNATE_DB)),)
		EXTRAFLAGS		+= --use-alternate-database $(ALTERNATE_DB)
	endif
endif
ifdef EXTRAFLAGS
	RUN_MASTER_CMD		+= $(EXTRAFLAGS)
	RUN_WORKER_CMD		+= $(EXTRAFLAGS)
endif

#/////////////////////////////////////////////////////////////////////////////|
# !!! DO NOT CHANGE ANYTHING BELOW THIS !!! ###################################
# (unless you know what you are doing) ########################################
#\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\|
mutator				:= mutator
test_subject		:= test_subject

# local dirs
prefix_dir			:= /usr/local/
mutator_dir			:= $(prefix_dir)$(mutator)/
tasKIT_dir			:= $(prefix_dir)tasKIT/
test_subject_dir	:= $(prefix_dir)$(test_subject)/
virtualenv_dir		:= $(prefix_dir)virtualenv_dir/
wrapper_dir			:= $(prefix_dir)wrapper/

# nfs dirs
nfs_dir				:= $(prefix_dir)data/
nfs_mutator_dir 	:= $(nfs_dir)$(mutator)/
nfs_test_subject_dir:= $(nfs_dir)$(test_subject)/

# python scripts
master_py			:= $(prefix_dir)master/master.py
worker_py			:= $(prefix_dir)worker/worker.py

# setup python scripts
setupWrapper_py		:= setupWrapper.py
setupLittleDarwin_py:= setupLittleDarwin.py
setupTasKIT_py		:= setup.py

# commands
system_pypy			:= /usr/bin/pypy

pip					:= $(virtualenv_dir)bin/pip
pypy				:= $(virtualenv_dir)bin/pypy

setup: setup_virtualenv pip_installs install_tasKIT install_wrapper install_mutator

setup_virtualenv:
	# setup virtual environment for pypy
	# this directly installs setuptools, pkg_resources, pip, wheel... in the virtualenv
	virtualenv -p $(system_pypy) $(virtualenv_dir)

pip_installs:
	# install pika (a RabbitMQ client for python) for pypy
	$(pip) install pika

install_mutator:
	# clone mutator into mutator dir
	git clone $(MUTATOR_REPOSITORY) $(mutator_dir) \
	&& `# go to specific commit or branch` \
	&& cd $(mutator_dir) \
	&& git checkout $(SPECIFIC_MUTATOR_COMMIT)
	# move LittleDarwin setup file into mutator &&
	# install mutator
	mv $(prefix_dir)$(setupLittleDarwin_py) $(mutator_dir) \
	&& cd $(mutator_dir) \
	&& $(pypy) $(setupLittleDarwin_py) install
	# remove repo to save space
	rm -rf $(mutator_dir)

install_test_subject:
	# copy the repository you want to test
	date +'Pre copy repo time is %d/%m/%Y %H:%M:%S:%3N'
	cp -R $(nfs_test_subject_dir) $(test_subject_dir)
	date +'Post copy repo is %d/%m/%Y %H:%M:%S:%3N'

install_tasKIT:
	# install tasKIT
	cd $(tasKIT_dir) \
	&& $(pypy) $(setupTasKIT_py) install

install_wrapper:
	# install wrapper defaults
	cd $(wrapper_dir) \
	&& $(pypy) $(setupWrapper_py) install

init_git:
	# add everything to git if no git repository detected
	cd $(test_subject_dir) \
	&& if [ -d .git ]; then \
			echo "git detected" \
			&& break; \
		else \
			echo "no git repo detected, adding everything to local git" \
			&& git init \
			&& git config user.name 'Snail Mail' \
			&& git config user.email '<>' \
			&& git add . \
			&& git commit -m "original src test_subject"; \
		fi

# this should never be necessary
remove:
	# remove test directory
	rm -rf $(test_subject_dir)
	# remove mutator directory
	rm -rf $(mutator_dir)

# reset to the original state
reset:
	cd $(test_subject_dir) \
	&& git clean -fd \
	&& git reset --hard

master: install_test_subject init_git
	# run the master
	cd $(prefix_dir) \
	&& trap 'make stop' SIGINT SIGTERM; $(RUN_MASTER_CMD) & echo $$! > running.PID && wait `cat running.PID`

worker: install_test_subject init_git
	# run the worker
	cd $(prefix_dir) \
	&& trap 'make stop' SIGINT SIGTERM; $(RUN_WORKER_CMD) & echo $$! > running.PID && wait `cat running.PID`

stop:
	kill -SIGTERM `cat running.PID` && rm running.PID

