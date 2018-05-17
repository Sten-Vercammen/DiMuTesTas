#!/usr/bin/env python

"""
    __     _  __   __   __       ____                          _
   / /    (_)/ /_ / /_ / /___   / __ \ ____ _ _____ _      __ (_)____
  / /    / // __// __// // _ \ / / / // __ `// ___/| | /| / // // __ \
 / /___ / // /_ / /_ / //  __// /_/ // /_/ // /    | |/ |/ // // / / /
/_____//_/ \__/ \__//_/ \___//_____/ \__,_//_/     |__/|__//_//_/ /_/

Copyright (C) 2014 Ali Parsai

This program is free software; you can redistribute it and/or
modify it under the terms of the GNU General Public License
as published by the Free Software Foundation; either version 2
of the License, or (at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with this program; if not, write to the Free Software
Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA  02110-1301, USA.

Ali Parsai
www.parsai.net
ali@parsai.net

"""

# generic imports
import shelve
import sys
import os
from optparse import OptionParser
import subprocess
import shutil

# LittleDarwin modules
import LittleDarwin
from JavaRead import JavaRead
from JavaParse import JavaParse
from JavaMutate import JavaMutate
import License
from ReportGenerator import ReportGenerator

# TimeIt module
import TimeIt

import logging

LOG_FORMAT = ('%(levelname) -10s %(asctime)s %(name) -30s %(funcName) '
              '-35s %(lineno) -5d: %(message)s')
LOGGER = logging.getLogger(__name__)


actual_options = None

@TimeIt.time_func
def copyDirectory(src, dest):
    try:
        shutil.copytree(src, dest)
    # Directories are the same
    except shutil.Error as e:
        LOGGER.debug('Directory not copied. Error: %s' % e)
    # Any error saying that the directory doesn't exist
    except OSError as e:
        LOGGER.debug('Directory not copied. Error: %s' % e)


def optionParser():
    # let's caution the user that we are using the alternative method.
    # if not timeoutSupport:
    #     print "!!! CAUTION !!!\nmodule subprocess32 not found. using alternative method. build procedure may hang in an infinite loop.\n\n"

    global actual_options

    if actual_options != None:
        return actual_options

    # parsing input options
    optionParser = OptionParser()

    optionParser.add_option("-m", "--mutate", action="store_true", dest="isMutationActive", default=False,
                            help="Activate the mutation phase.")
    optionParser.add_option("-b", "--build", action="store_true", dest="isBuildActive", default=False,
                            help="Activate the build phase.")
    optionParser.add_option("-v", "--verbose", action="store_true", dest="isVerboseActive", default=False,
                            help="Verbose output.")
    optionParser.add_option("-p", "--path", action="store", dest="sourcePath",
                            default=os.path.dirname(os.path.realpath(__file__)), help="Path to source files.")
    optionParser.add_option("-t", "--build-path", action="store", dest="buildPath",
                            default=os.path.dirname(os.path.realpath(__file__)), help="Path to build system working directory.")
    optionParser.add_option("-c", "--build-command", action="store", dest="buildCommand", default="mvn,test",
                            help="Command to run the build system. If it includes more than a single argument, they should be seperated by comma. For example: mvn,install")
    optionParser.add_option("--test-path", action="store", dest="testPath",
                            default="***dummy***", help="path to test project build system working directory")
    optionParser.add_option("--test-command", action="store", dest="testCommand", default="***dummy***",
                            help="Command to run the test-suite. If it includes more than a single argument, they should be seperated by comma. For example: mvn,test")
    optionParser.add_option("--initial-build-command", action="store", dest="initialBuildCommand",
                            default="***dummy***", help="Command to run the initial build.")
    optionParser.add_option("--timeout", type="int", action="store", dest="timeout", default=60,
                            help="Timeout value for the build process.")
    optionParser.add_option("--cleanup", action="store", dest="cleanUp", default="***dummy***",
                            help="Commands to run after each build.")
    optionParser.add_option("--use-alternate-database", action="store", dest="alternateDb", default="***dummy***",
                            help="Path to alternative database.")
    optionParser.add_option("--license", action="store_true", dest="isLicenseActive", default=False,
                            help="Output the license and exit.")
    optionParser.add_option("--higher-order", type="int", action="store", dest="higherOrder", default=1,
                            help="Define order of mutation. Use -1 to dynamically adjust per class.")
    optionParser.add_option("--null-check", action="store_true", dest="isNullCheck", default=False,
                            help="Use null check mutation operators.")

    optionParser.add_option("--all", action="store_true", dest="isAll", default=False,
                            help="Use all mutation operators.")

    (options, args) = optionParser.parse_args()

    if options.isLicenseActive:
        License.outputLicense()
        sys.exit(0)

    if options.higherOrder <= 1 and options.higherOrder != -1:
        options.higherOrder = 1

    actual_options = options
    return options


def symlink_nfs():
    options = optionParser()

    dst = os.path.abspath(os.path.join(os.path.abspath(options.sourcePath), os.path.pardir, "mutated"))
    if not os.path.exists(dst):
        src = '/usr/local/data/mutated'
        if not os.path.exists(src):
            os.makedirs(src)
        os.symlink(src, dst)


def unlink_nfs():
    # unlink symlink without removing data inside
    options = optionParser()

    dst = os.path.abspath(os.path.join(os.path.abspath(options.sourcePath), os.path.pardir, "mutated"))
    if os.path.isdir(dst):
        os.unlink(dst)

@TimeIt.time_func
def get_file_names():
    options = optionParser()

    assert options.isVerboseActive is not None
    # creating our module objects.
    javaRead = JavaRead(options.isVerboseActive)

    try:
        assert os.path.isdir(options.sourcePath)
    except AssertionError as exception:
        LOGGER.debug("source path must be a directory.")
        sys.exit(1)

    # getting the list of files.
    javaRead.listFiles(os.path.abspath(options.sourcePath))

    # undo creation of directories
    os.rmdir(javaRead.targetDirectory)

    return javaRead.fileList


def initial_build():
    try:
        symlink_nfs()

        with TimeIt.time_context('MutatorWrapper', 'initial_build'):
            options = optionParser()
            # initial build check to avoid false results. the system must be able to build cleanly without errors.

            try:
                if os.path.basename(options.buildPath) == "pom.xml":
                    assert os.path.isfile(options.buildPath)
                    buildDir = os.path.abspath(os.path.dirname(options.buildPath))
                else:
                    assert os.path.isdir(options.buildPath)
                    buildDir = os.path.abspath(options.buildPath)

            except AssertionError as exception:
                LOGGER.debug("build system working directory should be a directory.")

            # use build command for the initial build unless it is explicitly provided.
            if options.initialBuildCommand == "***dummy***":
                commandString = options.buildCommand.split(',')
            else:
                commandString = options.initialBuildCommand.split(',')

            LOGGER.info("Initial build... ")

            try:
                processKilled, processExitCode, initialOutput = LittleDarwin.timeoutAlternative(commandString,
                                                                                                workingDirectory=buildDir,
                                                                                                timeout=int(options.timeout))

                # initialOutput = subprocess.check_output(commandString, stderr=subprocess.STDOUT, cwd=buildDir)
                # workaround for older python versions
                if processKilled or processExitCode:
                    raise subprocess.CalledProcessError(1 if processKilled else processExitCode, commandString, initialOutput)
                with TimeIt.time_context('MutatorWrapper', 'writeInitialBuildOutput'):
                    with open(os.path.abspath(os.path.join(options.sourcePath, os.path.pardir, "mutated", "initialbuild.txt")),
                              'w+') as content_file:
                        content_file.write(initialOutput)
                LOGGER.info("done.\n\n")

            except subprocess.CalledProcessError as exception:
                initialOutput = exception.output
                with open(os.path.abspath(os.path.join(options.sourcePath, os.path.pardir, "mutated", "initialbuild.txt")),
                          'w+') as content_file:
                    content_file.write(initialOutput)
                LOGGER.info( "failed.\n\nInitial build failed. Try building the system manually first to make sure it can be built.:")
                LOGGER.info(exception)
                LOGGER.info(initialOutput)
                sys.exit(1)

        copyDirectory('/root/.m2', '/usr/local/data/.m2')
    finally:
        unlink_nfs()


@TimeIt.time_func
def generate_mutants(srcFile):
    try:
        symlink_nfs()

        options = optionParser()

        assert options.isVerboseActive is not None
        # creating our module objects.
        javaRead = JavaRead(options.isVerboseActive)
        javaParse = JavaParse(options.isVerboseActive)
        javaMutate = JavaMutate(javaParse, options.isVerboseActive)
        # set sourceDirectory
        javaRead.sourceDirectory = os.path.abspath(options.sourcePath)
        javaRead.targetDirectory = os.path.abspath(os.path.join(options.sourcePath, os.path.pardir, "mutated"))

        try:
            assert os.path.isdir(options.sourcePath)
        except AssertionError as exception:
            LOGGER.debug("source path must be a directory.")
            sys.exit(1)

        targetList = list()
        try:
            # parsing the source file into a tree.
            tree = javaParse.parse(javaRead.getFileContent(srcFile))

            # assigning a number to each node to be able to identify it uniquely.
            javaParse.numerify(tree)
            # javaParse.tree2DOT(tree)

        except Exception as e:
            # Java 8 problem
            LOGGER.debug("Error in parsing, skipping the file:")
            LOGGER.debug(e.message)
            sys.stderr.write(e.message)
            return [] #TODO how to handle this? (this works)

        if options.isAll:
            enabledMutators = "all"
        elif options.isNullCheck:
            enabledMutators = "null-check"
        else:
            enabledMutators = "classical"

        # apply mutations on the tree and receive the resulting mutants as a list of strings, and a detailed
        # list of which operators created how many mutants.
        mutated, mutantTypes = javaMutate.applyMutators(tree, options.higherOrder, enabledMutators)

        # for each mutant, generate the file, and add it to the list.
        for mutatedFile in mutated:
            targetList.append(javaRead.generateNewFile(srcFile, mutatedFile))

        # if the list is not empty (some mutants were found), return the mutants.
        mutants = list()
        key = os.path.relpath(srcFile, javaRead.sourceDirectory)
        for replacementFileRel in targetList:
            replacementFile = os.path.join(options.sourcePath, os.path.pardir, "mutated", replacementFileRel)
            mutants.append((key, replacementFileRel, replacementFile))
        return mutants
    finally:
        unlink_nfs()


@TimeIt.time_func
def _copy_dependencies_once(f):
    def copy_dependencies(*args, **kwargs):
        if not copy_dependencies.has_run:
            copy_dependencies.has_run = True
            copyDirectory('/usr/local/data/.m2', '/root/.m2')
        return f(*args, **kwargs)

    copy_dependencies.has_run = False
    return copy_dependencies


@_copy_dependencies_once
@TimeIt.time_func
def process_mutant(key, replacementFileRel, replacementFile):
    """
    e.g.
    replacementFileRel  = exampleCopy.java/3.java
    replacementFile     = Example/../mutated/exampleCopy.java/3.java
    """
    options = optionParser()
    original_f = False
    try:
        symlink_nfs()
        LOGGER.debug("testing mutant file: " + replacementFileRel)

        try:
            if os.path.basename(options.buildPath) == "pom.xml":
                assert os.path.isfile(options.buildPath)
                buildDir = os.path.abspath(os.path.dirname(options.buildPath))
            else:
                assert os.path.isdir(options.buildPath)
                buildDir = os.path.abspath(options.buildPath)

        except AssertionError as exception:
            LOGGER.debug("build system working directory should be a directory.")


        # check if we have separate test-suite
        if options.testCommand != "***dummy***":
            separateTestSuite = True
            if options.testPath == "***dummy***":
                testDir = buildDir
            else:
                try:
                    if os.path.basename(options.buildPath) == "pom.xml":
                        assert os.path.isfile(options.buildPath)
                        testDir = os.path.abspath(os.path.dirname(options.testPath))
                    else:
                        assert os.path.isdir(options.buildPath)
                        testDir = os.path.abspath(options.testPath)

                except AssertionError as exception:
                    LOGGER.debug("test project build system working directory should be a directory.")

        else:
            separateTestSuite = False


        success = False

        # run the build, store the results
        runOutputTest = ""

        with TimeIt.time_context('MutatorWrapper', 'readAndReplaceMutantFileForExecution'):
            # replace the original file with the mutant
            with open(replacementFile, 'r') as mutant_file:
                mutantFile = mutant_file.read()
            with open(os.path.join(options.sourcePath, key), 'r+') as f:
                f.seek(0)
                original_f = f.read()
                f.seek(0)
                f.write(mutantFile)
                f.truncate()

        commandString = options.buildCommand.split(',')
        if separateTestSuite:
            testCommandString = options.testCommand.split(',')

        try:
            # if we have timeout support, simply run the command with timeout support from subprocess32
            # if timeoutSupport:
            #     runOutput = subprocess.check_output(commandString, stderr=subprocess.STDOUT, cwd=buildDir,
            #                                         timeout=int(options.timeout))
            #     if separateTestSuite:
            #         runOutput += subprocess.check_output(testCommandString, stderr=subprocess.STDOUT, cwd=testDir,
            #                                         timeout=int(options.timeout))

            # else, run our alternative method
            # else:
            processKilled, processExitCode, runOutput = LittleDarwin.timeoutAlternative(commandString,
                                                                      workingDirectory=buildDir,
                                                                      timeout=int(options.timeout))

            # raise the same exception as the original check_output.
            if processKilled or processExitCode:
                raise subprocess.CalledProcessError(1 if processKilled else processExitCode, commandString,
                                                        runOutput)

            if separateTestSuite:
                processKilled, processExitCode, runOutputTest = LittleDarwin.timeoutAlternative(testCommandString,
                                                      workingDirectory=testDir, timeout=int(options.timeout))

                # raise the same exception as the original check_output.
                if processKilled or processExitCode:
                    raise subprocess.CalledProcessError(1 if processKilled else processExitCode,
                                                      commandString, "\n".join([runOutput, runOutputTest]))


            # if we are here, it means no exceptions happened, so lets add this to our success list.
            runOutput += "\n" + runOutputTest
            success = True

        # putting two exceptions in one except clause, specially when one of them is not defined on some
        # platforms does not look like a good idea; even though both of them do exactly the same thing.
        except subprocess.CalledProcessError as exception:
            runOutput = exception.output
            # oops, error. let's keep this as a failure.

        # except subprocess.TimeoutExpired as exception:
        #     runOutput = exception.output
        #     failureList.append(os.path.basename(replacementFile))

        # if there's a cleanup option, execute it. the results will be ignored because we don't want our process
        #  to be interrupted if there's nothing to clean up.
        if options.cleanUp != "***dummy***":
            subprocess.call(options.cleanUp.split(","), cwd=buildDir)
            if separateTestSuite:
                subprocess.call(options.cleanUp.split(","), cwd=testDir)

        # find path to write runOutput to
        targetTextOutputFile = os.path.splitext(replacementFile)[0] + ".txt"

        with TimeIt.time_context('MutatorWrapper', 'writeMutantBuildOutput'):
            # writing the build output to disk.
            with open(targetTextOutputFile, 'w') as content_file:
                content_file.write(runOutput)

        return {'key': key,
                'success': success,
                'replacementFile': replacementFile}
    finally:
        unlink_nfs()
        if original_f is not False:
            with open(os.path.join(options.sourcePath, key), 'r+') as f:
                f.seek(0)
                f.write(original_f)
                f.truncate()

@TimeIt.time_func
def process_result(key, success, replacementFile):
    try:
        symlink_nfs()

        options = optionParser()

        # get database path
        if options.alternateDb == "***dummy***":
            databasePath = os.path.abspath(os.path.join(options.sourcePath, os.path.pardir, "mutated", "mutationdatabase"))
        else:
            databasePath = options.alternateDb

        statisticDatabasePath = databasePath + "-statistics"
        # open database for reading and writing

        statisticsDB = None
        try:
            statisticsDB = shelve.open(statisticDatabasePath, "c", writeback=True)
            #workaround:
            #shutil.rmtree(os.path.join(testDir,"VolumetryLoggerTest"),ignore_errors=True)

            # check if key exists
            if statisticsDB.get(key) != None:
                statisticsDB[key][1 if success else 0].append(os.path.basename(replacementFile))
            else:
                successList = list()
                failureList = list()
                if success:
                    successList.append(os.path.basename(replacementFile))
                else:
                    failureList.append(os.path.basename(replacementFile))
                statisticsDB[key] = (failureList, successList)
        finally:
            if statisticsDB is not  None:
                statisticsDB.close()
    finally:
        unlink_nfs()

@TimeIt.time_func
def generate_report():
    try:
        symlink_nfs()
        # all generated mutants are processed

        options = optionParser()

        # get database path
        if options.alternateDb == "***dummy***":
            databasePath = os.path.abspath(os.path.join(options.sourcePath, os.path.pardir, "mutated", "mutationdatabase"))
        else:
            databasePath = options.alternateDb

        statisticDatabasePath = databasePath + "-statistics"

        textReportData = list()
        htmlReportData = list()

        reportGenerator = ReportGenerator()

        if options.alternateDb == "***dummy***":
            databasePath = os.path.abspath(
                os.path.join(options.sourcePath, os.path.pardir, "mutated", "mutationdatabase"))
        else:
            databasePath = options.alternateDb

        resultsDatabasePath = databasePath + "-results"
        reportGenerator.initiateDatabase(resultsDatabasePath)

        # open database for reading and writing
        statisticsDB = None
        try:
            statisticsDB = shelve.open(statisticDatabasePath, "c")
            # let's sort the files by name, so that we can created a alphabetical report.
            databaseKeys = statisticsDB.keys()
            databaseKeys.sort()
            for key in databaseKeys:
                (failureList, successList) = statisticsDB[key]
                #replacementFile = successList[-1] if len(successList) > 0 else failureList[-1]
                replacementFile = os.path.join(options.sourcePath, os.path.pardir, "mutated", key + '/' + (successList[-1] if len(successList) > 0 else failureList[-1]))

                # all mutants must be checked by now, so we should have a complete divide between success and failure.
                mutantCount = len(successList) + len(failureList)

                # append the information for this file to the reports.
                textReportData.append(key + ": survived (" + str(len(successList)) + "/" + str(mutantCount) + ") -> " + str(
                    successList) + " - killed (" + str(len(failureList)) + "/" + str(mutantCount) + ") -> " + str(
                    failureList) + "\r\n")
                htmlReportData.append([key, len(successList), mutantCount])

                # generate an HTML report for the file.
                targetHTMLOutputFile = os.path.join(os.path.dirname(replacementFile), "results.html")
                with open(targetHTMLOutputFile, 'w') as content_file:
                    content_file.write(
                        reportGenerator.generateHTMLReportPerFile(key, targetHTMLOutputFile, successList, failureList))
        finally:
            if statisticsDB is not None:
                statisticsDB.close()

        # write final text report.
        with open(os.path.abspath(os.path.join(options.sourcePath, os.path.pardir, "mutated", "report.txt")),
                  'w') as textReportFile:
            textReportFile.writelines(textReportData)

        # write final HTML report.
        targetHTMLReportFile = os.path.abspath(
            os.path.join(options.sourcePath, os.path.pardir, "mutated", "report.html"))
        with open(targetHTMLReportFile, 'w') as htmlReportFile:
            htmlReportFile.writelines(reportGenerator.generateHTMLFinalReport(htmlReportData, targetHTMLReportFile))
    except Exception as e:
        LOGGER.debug(e)
    finally:
        unlink_nfs()
