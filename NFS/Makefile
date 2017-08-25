# Makefile for easy listing of commands

# change this depending on the repository you want to use for testing
TEST_REPOSITORY	:= https://github.com/addthis/codec.git
# specific commit or branch-name
SPECIFIC_TEST_COMMIT	:= 1bbddc652ee4a9ee7e6b0d5ca1cf0a5d930e9f95
# example to checkout master:
# SPECIFIC_TEST_COMMIT	:= master


###############################################################################
# !!! DO NOT CHANGE ANYTHING BELOW THIS !!! ###################################
# (unless you know what you are doing) ########################################
###############################################################################

test_subject_dir		:= test_subject

pull: pull_test_subject

pull_test_subject:
	# clone test subject into test subject dir
	git clone $(TEST_REPOSITORY) $(test_subject_dir) \
	&& `# go to specific commit or branch` \
	&& cd $(test_subject_dir) \
	&& git checkout $(SPECIFIC_TEST_COMMIT)