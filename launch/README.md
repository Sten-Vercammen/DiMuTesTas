# Setup Docker swarm

For the tool to work, a Docker swarm must exist.
Creating the swarm can be done by: `docker swarm init`

This command will print the join command that needs to be run on other nodes in order to add them as workers to the swarm.


To allow communication between the different Docker containers, we need to setup our own overlay network by executing the create\_overlay\_network.sh script.

Building the Docker images can be done by executing the build\_images.sh script inside the launch folder. (Building the images must be done on each node as we have not uploaded them to Docker Hub.)


# Executing the distributed tool
Running the tool is done by executing the run.sh script.
This requires an NFS (or other fileserver, which requires changes inside the run.sh script). (For Ubuntu, this also means that each node should have the nfs-common package installed.)

Inside the run.sh script, the location (IP Address) of the NFS needs to be configured, by changing the ST_SRC. We also need to provide it with which directory on the NFS is being exported and used to connect with by changing the ST_DEVICE.

Underlying, LittleDarwin is used and we can change all variables exposed by it (see later).
To understand the different parameters, see [http://littledarwin.parsai.net/release/littledarwin-manpage.pdf](http://littledarwin.parsai.net/release/littledarwin-manpage.pdf)

## Default parameters
	* BUILDCOMMAND = mvn, test
	* SOURCEPATH = src/main/
	* others are equal to the defaults of LittleDarwin
Changing these should suffice for most straightforward repositories.

# Customisation and test repository setup:
	1. Clone test repository onto NFS in a folder called ``test_subject’’
		(e.g. in NFS’s makefile: setup_test_subject)
	2. Change parameters in run.sh script, by adding -e PARAMETER1=your-value -e PARAMETER2=your-value to the master and workers ``docker service create’’ command.
		2.1. If your repository uses a different build command to run the tests (and/or uses ant), you need to change the BUILDCOMMAND
		2.2. You can change the source path by changing the SOURCEPATH variable.

The complete list of changeable variables can be found below:

	* SOURCEPATH
	* BUILDPATH
	* BUILDCOMMAND
	* TESTPATH
	* TESTCOMMAND
	* INITIALBUILDCOMMAND
	* TIMEOUT
	* CLEANUP
	* ALTERNATEDB
(These correspond to the ones on [http://littledarwin.parsai.net/release/littledarwin-manpage.pdf](http://littledarwin.parsai.net/release/littledarwin-manpage.pdf))



# Show the timings
To show the timings, comment line 101 in run.sh.
After the master finishes, stop each container individually by:
docker kill --signal SIGTERM <workerID>
then save its logs by:
docker logs <workerID> &> <workerX.txt>
The timings of the master can be found in a simular way
(master ends on its own, so you do not need to stop it)
docker logs <masterID> &> <master.txt>
