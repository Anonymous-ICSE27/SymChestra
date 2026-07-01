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
    argparser.add_argument('--n_scores', default=20, type=int)
    argparser.add_argument('--main_option', default='featmaker')
    argparser.add_argument('--eta_num', default=10)


    # Symtuner Parser
    argparser.add_argument('-s', '--search-space', default='/root/symchestra/benchmarks/spaces-featmaker.json', type=str, metavar='JSON',
                                 help='Json file defining parameter search space')
    argparser.add_argument('--exploit-portion', default=0.7, type=float, metavar='FLOAT',
                                 help='Portion of exploitation in SymTuner (default=0.7)')
    argparser.add_argument('--step', default=20, type=int, metavar='INT',
                                 help='The number of symbolic execution runs before increasing small budget (default=20)')
    argparser.add_argument('--minimum-time-portion', default=0.005, type=float, metavar='FLOAT',
                                 help='Minimum portion for one iteration (default=0.005)')
    argparser.add_argument('--increase-ratio', default=2, type=float, metavar='FLOAT',
                                 help='A number that is multiplied to increase small budget. (default=2)')
    argparser.add_argument('--minimum-time-budget', default=30, type=int, metavar='INT',
                                 help='Minimum time budget to perform symbolic execution (default=30)')
    argparser.add_argument('--exploration-steps', default=20, type=int, metavar='INT',
                                 help='The number of symbolic execution runs that SymTuner focuses only on exploration (default=20)')

    # Others
    argparser.add_argument('--generate-search-space-json', action='store_true',
                        help='Generate the json file defining parameter spaces used in our ICSE\'22 paper')
    argparser.add_argument('--debug', action='store_true',
                        help='Log the debug messages')
    argparser.add_argument('--gcov-depth', default=1, type=int,
                        help='Depth to search for gcda and gcov files from gcov_obj to calculate code coverage (default=1)')

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
        os.mkdir(f"{top_dir}/weight")
        os.mkdir(f"{top_dir}/features")

        coverage_csv = Path(f"{top_dir}/coverage.csv")
        coverage_csv.touch()
        get_logger().info(
            f'Coverage will be recoreded at "{coverage_csv}" at every iteration.')

        found_bugs_txt = Path(f"{top_dir}/found_bugs.txt")
        found_bugs_txt.touch()
        get_logger().info(
            f'Found bugs will be recoreded at "{found_bugs_txt}" at every iteration.')

    else:
        print("Output directory is already existing")
        exit(1)

    # Symtuner Setting
    if arguments.debug:
        get_logger().setLevel('DEBUG')

    if arguments.generate_search_space_json:
        space_json = KLEESymTuner.get_default_space_json()
        with Path('example-space.json').open('w') as stream:
            json.dump(space_json, stream, indent=4)
            get_logger().info('Example space configuration json is generated: example-space.json')
        sys.exit(0)

    symtuner = KLEESymTuner('/root/symchestra/klee_featmaker/build/bin/klee-replay', 'gcov', 10, arguments.search_space, arguments.exploit_portion)
    evaluation_argument = {'folder_depth': arguments.gcov_depth}

    pconfig = load_pgm_config(f"configs/{pgm}.json")
    pconfig["gcov_path"] = os.getcwd() + "/" + pconfig["gcov_path"] + pconfig["exec_dir"]
    llvm_dir = os.getcwd() + "/" + pconfig["pgm_dir"]
    os.system(f"cp -r {llvm_dir} {top_dir}/")

    fg = feature_generator.feature_generator(data, top_dir, arguments)

    if arguments.main_option == "featmaker":
        wg = weight_generator.learning_weight_generator(data, top_dir, arguments.n_scores)
    else:
        wg = weight_generator.random_weight_generator(data, top_dir, arguments.n_scores)
    ke = klee_executor.klee_executor(pconfig, top_dir, arguments, symtuner, wg)

    data = {}
    start_time = time.time()
    iteration = 0
 
    print("Before Start")    

    get_logger().info('All configuration loaded. Start testing.')
    time_budget_handler = TimeBudgetHandler(arguments.total_budget, arguments.minimum_time_portion, arguments.step, arguments.increase_ratio, arguments.minimum_time_budget)
    
    cur_dir = os.getcwd()
    rm_cmd = ' '.join(['rm', '-rf', pconfig['gcov_file'], pconfig['gcda_file']])
    
    sym_step = 0
    feat_step = 0
    ram_step = 0

    feat_iter = 0
    weight_idx = 0

    allCoverage = set()
    curCoverage = set()
    
    count = 0
    execCount = 0
    
    branchFrequency = defaultdict(int)
    datastructure = {"symtuner" : dict(), "featmaker" : dict(), "ram" : dict()}
    querystructure = set()
    usedBuffer = list()

    os.mkdir(f"{top_dir}/result/symtuner")
    os.mkdir(f"{top_dir}/result/iteration-{feat_iter}")
    os.mkdir(f"{top_dir}/weight/iteration-{feat_iter}")
    os.mkdir(f"{top_dir}/result/ram")
    execution_num = 0

    mode = "symtuner"
    modeFirst = False
    firstTrain = True
    parameters = dict()
    goodorbad = False
    nextSeed = None
    badQueries = None

    returnSeeds.set_eta_num(int(arguments.eta_num))
    max_time = 120
    parameters['-max-time'] = max_time
    symtuner.mode = "featmaker"
    
    ### FIRST TRAIN
    while firstTrain:
        parameters['-output-dir'] = f"{top_dir}/result/iteration-{feat_iter}/{feat_step}"
        testcases_featmaker = ke.execute_klee(iteration=feat_iter, parameters=parameters, weight_idx=weight_idx, get_logger=get_logger, 
                                              flag="featmaker", flag2="parallel")
        symtuner.add(pconfig, testcases_featmaker, parameters=parameters, evaluation_kwargs=evaluation_argument, rm_cmd=rm_cmd, flag="basefeatmaker")

        symtuner.featmakerdata.append(dict())
        for key, value in symtuner.tempfeatmakerdata.items():
            symtuner.featmakerdata[weight_idx][key] = value
            
        feat_step += 1  
        weight_idx += 1      

        elapsed = time_budget_handler.elapsed
        allCoverage |= symtuner.allCoverage
        execCount += 1

        get_logger().info(f'Execution Number: {execution_num + 1} '
                          f'Time budget: 120 '
                          f'Mode : {mode} '
                          f'Time elapsed: {elapsed} '
                          f'All Coverage: {len(allCoverage)} '
                          f'Steps: {sym_step} {feat_step} '
                          f'Count: {count} '
                          f'execCount : {execCount}')

        if execCount % arguments.n_scores == 0 and execCount != 0:
            firstTrain = False
            count = 0
            execCount = 0

            feat_iter += 1

            os.mkdir(f"{top_dir}/result/iteration-{feat_iter}")
            os.mkdir(f"{top_dir}/weight/iteration-{feat_iter}")

            print(f"Generate features in iteration: {feat_iter - 1}")
            fg.n_scores = len(symtuner.featmakerdata)
            fg.collect(feat_iter, symtuner.featmakerdata)
            fg.extract_feature()

            print(f"Generate weights in iteration: {feat_iter - 1}")
            wg.n_weights = len(symtuner.featmakerdata)
            wg.generate_weight(feat_iter)
            ke.feat_len = len(wg.data["features"])
              
        
        with coverage_csv.open('a') as stream:
            stream.write(f'{elapsed}, {len(allCoverage)}\n')

        execution_num += 1


    weight_idx = 0
    feat_step = 0
    symtuner.mode = mode

    for i, _ in enumerate(time_budget_handler):
        if mode == "symtuner":
            if modeFirst:
                if len(symtuner.parallelram) != 0:
                    modeFirst = False
                else:                
                    weight_idx = None

            policy = 'explore' if sym_step < arguments.exploration_steps else None
            parameters = symtuner.sample(policy=policy)

            parameters['-output-dir'] = f"{top_dir}/result/symtuner/{sym_step}"
            parameters['-max-time'] = max_time
            
            testcases_symtuner = ke.execute_klee(iteration=feat_iter - 1, parameters=parameters, weight_idx=weight_idx, get_logger=get_logger, 
                                                flag="symtuner", flag2="parallel", ram=goodorbad, 
                                                seed=nextSeed, badQueries=badQueries)
            symtuner.add(pconfig, testcases_symtuner, parameters=parameters, evaluation_kwargs=evaluation_argument, rm_cmd=rm_cmd, flag="basesymtuner")

            for each in symtuner.tempsymdata:
                symtuner.data.append(each)

                if filterSeeds.checkAndUpdateQueries(each[2], querystructure):
                    datastructure[mode][each[2]] = each[0]
    
            symtuner.combination_version_add()
            sym_step += 1

        elif mode == "featmaker":
            if len(symtuner.parallelsymtuner) != 0 and modeFirst:
                modeFirst = False
                symtuner.parallelfeatmaker = []

                bestP = -1e10
                parameters = None
                bestBranch = None

                for index in range(len(symtuner.parallelsymtuner)):
                    curSymTuner = symtuner.parallelsymtuner[index]

                    curSymTunerParam, curSymTunerBranch, curSymTunerErrorNum = curSymTuner

                    score = 0.0

                    for branch in curSymTunerBranch:
                        score += 1 / symtuner.branchFrequency[branch]

                    score += curSymTunerErrorNum

                    if bestP < score:
                        bestP = score
                        parameters = curSymTunerParam
                        bestBranch = curSymTunerBranch

                # Update Frequency
                for branch in bestBranch:
                    symtuner.branchPerScore["symtuner"][branch] = symtuner.branchPerScore["symtuner"].get(branch) * 1.1

            parameters['-output-dir'] = f"{top_dir}/result/iteration-{feat_iter}/{feat_step}"
            parameters['-max-time'] = max_time
            
            testcases_featmaker = ke.execute_klee(iteration=feat_iter, parameters=parameters, weight_idx=weight_idx, get_logger=get_logger, 
                                                  flag="symtuner", flag2="parallel", ram=goodorbad, 
                                                  seed=nextSeed, badQueries=badQueries)
            symtuner.add(pconfig, testcases_featmaker, parameters=parameters, evaluation_kwargs=evaluation_argument, rm_cmd=rm_cmd, flag="basefeatmaker")

            symtuner.featmakerdata.append(dict())
            for key, value in symtuner.tempfeatmakerdata.items():
                symtuner.featmakerdata[weight_idx][key] = value

                if filterSeeds.checkAndUpdateQueries(key, querystructure):
                    datastructure[mode][key] = value
            
            feat_step += 1  
            weight_idx += 1 

        elif mode == "ram":
            if modeFirst:
                if len(symtuner.parallelfeatmaker) != 0:
                    modeFirst = False
                    symtuner.parallelsymtuner = []

                    bestFW = -1e10
                    weight_idx = None
                    bestBranch = None
                    for index in range(len(symtuner.parallelfeatmaker)):
                        curFeatMaker = symtuner.parallelfeatmaker[index]

                        curFeatMakerBranch, curFeatMakerErrorNum = curFeatMaker

                        score = 0.0

                        for branch in curFeatMakerBranch:
                            score += 1 / symtuner.branchFrequency[branch]
                        
                        score += curFeatMakerErrorNum

                        if bestFW < score:
                            bestFW = score
                            weight_idx = index
                            bestBranch = curFeatMakerBranch

                    # Update Frequency
                    for branch in bestBranch:
                        symtuner.branchPerScore["featmaker"][branch] = symtuner.branchPerScore["featmaker"].get(branch) * 1.1    

                else:                
                    weight_idx = None

            parameters['-output-dir'] = f"{top_dir}/result/ram/{ram_step}"
            parameters['-max-time'] = max_time
            
            testcases_symtuner = ke.execute_klee(iteration=feat_iter - 1, parameters=parameters, weight_idx=weight_idx, get_logger=get_logger, 
                                                flag="symtuner", flag2="parallel", ram=goodorbad, 
                                                seed=nextSeed, badQueries=badQueries)
            symtuner.add(pconfig, testcases_symtuner, parameters=parameters, evaluation_kwargs=evaluation_argument, rm_cmd=rm_cmd, flag="baseram")

            for each in symtuner.tempramdata:
                if filterSeeds.checkAndUpdateQueries(each[1], querystructure):
                    datastructure[mode][each[1]] = each[0]
    
                branches = each[0]
            
            ram_step += 1

        elapsed = time_budget_handler.elapsed
        coverage, bugs = symtuner.get_coverage_and_bugs()
        allCoverage = coverage | symtuner.tempfeatmakerCoverage
        execCount += 1
        
        if len(curCoverage) == len(allCoverage):
            count += 1
        else:
            count = 0

        get_logger().info(f'Execution Number: {i + 1} '
                          f'Time budget: 120 '
                          f'Mode : {mode} '
                          f'Time elapsed: {elapsed} '
                          f'Coverage: {len(curCoverage)} '
                          f'All Coverage: {len(allCoverage)} '
                          f'Steps: {sym_step} {feat_step} {ram_step} '
                          f'Count: {count} '
                          f'execCount : {execCount}')

        curCoverage = allCoverage.copy()
            
        if execCount % arguments.n_scores == 0 and execCount != 0:
            modeFirst = True
            count = 0
            
            
            nextSeed, badQueries = returnSeeds.returnBestFilteredSeedBadDifferentQueries(mode, datastructure, symtuner.branchFrequency, usedBuffer,
                                                                                         symtuner=symtuner)
            if mode == "symtuner":
                mode = "featmaker"
                weight_idx = 0
                execCount = 0
                feat_step = 0
                symtuner.featmakerdata = []
                print("=" * 70)

            elif mode == "featmaker":
                mode = "ram"
                execCount = 0

                feat_iter += 1
                featCov = allCoverage.copy()

                os.mkdir(f"{top_dir}/result/iteration-{feat_iter}")
                os.mkdir(f"{top_dir}/weight/iteration-{feat_iter}")
                print(f"Generate features in iteration: {feat_iter - 1}")
                fg.n_scores = len(symtuner.featmakerdata)
                fg.collect(feat_iter, symtuner.featmakerdata)
                fg.extract_feature()
                print(f"Generate weights in iteration: {feat_iter - 1}")
                wg.n_weights = len(symtuner.featmakerdata)
                wg.generate_weight(feat_iter)
                ke.feat_len = len(wg.data["features"])
                print("=" * 70)

                goodorbad = True

            elif mode == "ram":
                mode = "symtuner"
                execCount = 0
                goodorbad = False

        elif count == 5:
            count = 0
            modeFirst = True

            nextSeed, badQueries = returnSeeds.returnBestFilteredSeedBadDifferentQueries(mode, datastructure, symtuner.branchFrequency, usedBuffer,
                                                                                        symtuner=symtuner)
            if mode == "symtuner":
                mode = "featmaker"
                weight_idx = 0
                execCount = 0

                symtuner.featmakerdata = []
                print("=" * 70)

            elif mode == "featmaker":
                mode = "ram"
                execCount = 0

                feat_iter += 1

                os.mkdir(f"{top_dir}/result/iteration-{feat_iter}")
                os.mkdir(f"{top_dir}/weight/iteration-{feat_iter}")
                print(f"Generate features in iteration: {feat_iter - 1}")
                fg.n_scores = len(symtuner.featmakerdata)
                fg.collect(feat_iter, symtuner.featmakerdata)
                fg.extract_feature()
                print(f"Generate weights in iteration: {feat_iter - 1}")
                wg.n_weights = len(symtuner.featmakerdata)
                wg.generate_weight(feat_iter)
                ke.feat_len = len(wg.data["features"])     
                print("=" * 70)
            
                goodorbad = True
        
            elif mode == "ram":
                mode = "symtuner"
                execCount = 0
                goodorbad = False

        with coverage_csv.open('a') as stream:
            stream.write(f'{elapsed}, {len(allCoverage)}\n')
        with found_bugs_txt.open('w') as stream:
            stream.writelines((f'Testcase: {Path(symtuner.get_testcase_causing_bug(bug)).absolute()} '
                               f'Bug: {bug}\n' for bug in bugs))

        execution_num += 1
        symtuner.mode = mode

    os.chdir(root_dir)
            
    coverage, bugs = symtuner.get_coverage_and_bugs()
    get_logger().info(f'SymChestra-based integration of SymTuner+FeatMaker+RAM achieved {len(coverage)} coverage.')