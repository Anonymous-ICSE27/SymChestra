from subprocess import Popen, PIPE
from collections import defaultdict
from pathlib import Path
import json
import time
import os
import optparse
import argparse
import pickle
import shutil
import sys

from featmaker_subscript import klee_executor
from featmaker_subscript import feature_generator
from featmaker_subscript import weight_generator

from symchestra_subscript import returnSeeds
from symchestra_subscript import filterSeeds

from klee import KLEE
from klee import KLEESymTuner
from logger import get_logger
from symtuner import TimeBudgetHandler

def load_pgm_config(config_file):
    with open(config_file, 'r') as f:
        parsed = json.load(f)
    return parsed

if __name__=="__main__":
    parser = optparse.OptionParser()
    argparser = argparse.ArgumentParser()
    
    # Required Options
    argparser.add_argument('pgm')
    argparser.add_argument('output_dir')
    argparser.add_argument('--total_budget', default=86400)
    argparser.add_argument('--debug', action='store_true', help='Log the debug messages')
    arguments = argparser.parse_args()

    if arguments.pgm is None:
        print("Required option is empty: pgm")
        exit(1)
        
    if arguments.output_dir is None:
        print("Required option is empty: output_dir")
        exit(1)
            
    pgm = arguments.pgm
    output_dir = arguments.output_dir

    exp_dir = f"symchestra_experiments"
    top_dir = f"/root/symchestra/{exp_dir}/{output_dir}/{pgm}"
    root_dir = os.getcwd()
    data = {}

    if not os.path.exists(top_dir):
        os.makedirs(top_dir)
        os.mkdir(f"{top_dir}/result")
        os.mkdir(f"{top_dir}/data")

        coverage_csv = Path(f"{top_dir}/coverage.csv")
        coverage_csv.touch()
        get_logger().info(
            f'Coverage will be recoreded at "{coverage_csv}" at every iteration.')

        found_bugs_txt = Path(f"{top_dir}/found_bugs.txt")
        found_bugs_txt.touch()
        get_logger().info(
            f'Found bugs will be recoreded at "{found_bugs_txt}" at every iteration.')

    else:
        print("Output directory is already existing. You need to remove the direcotry")
        exit(1)

    # Symtuner Setting
    if arguments.debug:
        get_logger().setLevel('DEBUG')

    symtuner = KLEESymTuner('/root/symchestra/klee_featmaker/build/bin/klee-replay', 'gcov', 10, arguments.search_space, arguments.exploit_portion)
    evaluation_argument = {'folder_depth': arguments.gcov_depth}

    pconfig = load_pgm_config(f"configs/{pgm}.json")
    pconfig["gcov_path"] = os.getcwd() + "/" + pconfig["gcov_path"] + pconfig["exec_dir"]
    llvm_dir = os.getcwd() + "/" + pconfig["pgm_dir"]
    os.system(f"cp -r {llvm_dir} {top_dir}/")

    ke = klee_executor.klee_executor(pconfig, top_dir, arguments, symtuner)

    data = {}
    start_time = time.time()
    print("Before Start")    

    get_logger().info('All configuration loaded. Start testing.')
    time_budget_handler = TimeBudgetHandler(arguments.total_budget, arguments.minimum_time_portion, arguments.step, arguments.increase_ratio, arguments.minimum_time_budget)

    cur_dir = os.getcwd()
    rm_cmd = ' '.join(['rm', '-rf', pconfig['gcov_file'], pconfig['gcda_file']])
    
    ram_step = 0
    allCoverage = set()
    
    os.mkdir(f"{top_dir}/result/ram")

    parameters = dict()
    parameters['-max-time'] = max_time

    for ram_step, _ in enumerate(time_budget_handler):
        parameters['-output-dir'] = f"{top_dir}/result/ram/{ram_step}"
        parameters['-max-time'] = 3600
        
        testcases_symtuner = ke.execute_klee(iteration=-1, parameters=parameters, weight_idx=None, get_logger=get_logger, 
                                            flag="symtuner", flag2="parallel", ram=True)
        symtuner.add(pconfig, testcases_symtuner, parameters=parameters, evaluation_kwargs=evaluation_argument, rm_cmd=rm_cmd, flag="baseram")
        symtuner.combination_version_add()
        
        elapsed = time_budget_handler.elapsed
        coverage, bugs = symtuner.get_coverage_and_bugs()
        allCoverage = coverage | symtuner.tempfeatmakerCoverage
        
        get_logger().info(f'Execution Number: {i + 1} '
                          f'Time budget: 3600 '
                          f'Time elapsed: {elapsed} '
                          f'All Coverage: {len(allCoverage)}')

        with coverage_csv.open('a') as stream:
            stream.write(f'{elapsed}, {len(allCoverage)}\n')
        with found_bugs_txt.open('w') as stream:
            stream.writelines((f'Testcase: {Path(symtuner.get_testcase_causing_bug(bug)).absolute()} '
                               f'Bug: {bug}\n' for bug in bugs))

    os.chdir(root_dir)
            
    coverage, bugs = symtuner.get_coverage_and_bugs()
    get_logger().info(f'Standalone KLEE-RAM achieved {len(coverage)} coverage.')