from collections import defaultdict
from pathlib import Path
import argparse
import json
import os
import sys

from homi_func import Feature_Extractor
from homi_func import PruningStgy_Generator
from homi_func import Run_KLEE
from homi_func import Run_gcov
from homi_func import SetCoverProblem
from klee import KLEESymTuner
from logger import get_logger
from symtuner import TimeBudgetHandler


BASE_DIR = Path(__file__).resolve().parent


def load_pgm_config(config_file):
    with open(config_file, 'r') as f:
        parsed = json.load(f)
    return parsed


if __name__ == "__main__":
    argparser = argparse.ArgumentParser()

    # Required Options
    argparser.add_argument('pgm')
    argparser.add_argument('output_dir')
    argparser.add_argument('--search-heuristic', default='roundrobin')
    argparser.add_argument('--core-num', default='1')
    argparser.add_argument('--total_budget', default=86400, type=int)
    argparser.add_argument('--n_scores', default=20, type=int)

    # Symtuner Parser
    argparser.add_argument('-s', '--search-space',
                           default=str(BASE_DIR / 'benchmarks' / 'spaces-homi.json'),
                           type=str, metavar='JSON',
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
                           help='Generate the json file defining parameter spaces')
    argparser.add_argument('--debug', action='store_true',
                           help='Log the debug messages')
    argparser.add_argument('--gcov-depth', default=1, type=int,
                           help='Depth to search for gcda and gcov files from gcov_obj to calculate code coverage (default=1)')

    arguments = argparser.parse_args()

    if arguments.pgm is None:
        print("Required option is empty: pgm")
        sys.exit(1)

    if arguments.output_dir is None:
        print("Required option is empty: output_dir")
        sys.exit(1)

    pgm = arguments.pgm
    output_dir = arguments.output_dir

    exp_dir = "symchestra_experiments"
    top_dir = BASE_DIR / exp_dir / output_dir / pgm
    root_dir = os.getcwd()
    data = {}

    if not top_dir.exists():
        top_dir.mkdir(parents=True)
        (top_dir / "result").mkdir()
        (top_dir / "weight").mkdir()
        (top_dir / "errors").mkdir()
        (top_dir / "features").mkdir()
        (top_dir / "data").mkdir()

        coverage_csv = top_dir / "coverage.csv"
        coverage_csv.touch()
        get_logger().info(
            f'Coverage will be recoreded at "{coverage_csv}" at every iteration.')

        found_bugs_txt = top_dir / "found_bugs.txt"
        found_bugs_txt.touch()
        get_logger().info(
            f'Found bugs will be recoreded at "{found_bugs_txt}" at every iteration.')
    else:
        print("Output directory is already existing")
        sys.exit(1)

    if arguments.debug:
        get_logger().setLevel('DEBUG')

    if arguments.generate_search_space_json:
        space_json = KLEESymTuner.get_default_space_json()
        with Path('example-space.json').open('w') as stream:
            json.dump(space_json, stream, indent=4)
            get_logger().info('Example space configuration json is generated: example-space.json')
        sys.exit(0)

    symtuner = KLEESymTuner(str(BASE_DIR / 'klee_feathomi' / 'build' / 'bin' / 'klee-replay'),
                            'gcov', 10, arguments.search_space, arguments.exploit_portion)
    evaluation_argument = {'folder_depth': arguments.gcov_depth}

    pconfig = load_pgm_config(BASE_DIR / "configs" / f"{pgm}.json")
    pconfig["gcov_path"] = str(BASE_DIR / pconfig["gcov_path"] / pconfig["exec_dir"].lstrip("/"))
    pconfig["pgm_dir"] = str(BASE_DIR / pconfig["pgm_dir"])
    llvm_dir = pconfig["pgm_dir"]
    os.system(f"cp -r {llvm_dir} {top_dir}/")

    get_logger().info('All configuration loaded. Start testing.')
    time_budget_handler = TimeBudgetHandler(arguments.total_budget,
                                            arguments.minimum_time_portion,
                                            arguments.step,
                                            arguments.increase_ratio,
                                            arguments.minimum_time_budget)

    cur_dir = os.getcwd()
    rm_cmd = ' '.join(['rm', '-rf', pconfig['gcov_file'], pconfig['gcda_file']])

    feat_iter = 0
    weight_idx = 0
    homi_step = 0
    homi_iter = 0

    allCoverage = set()
    beforeCoverage = set()
    execCount = 0
    branchFrequency = defaultdict(int)
    homi_data_path = []
    homi_data = {}

    (top_dir / "result" / f"iteration-{feat_iter}").mkdir()
    (top_dir / "weight" / f"iteration-{feat_iter}").mkdir()
    execution_num = 0

    tool = "homi"
    d_name = "All"
    stgy = arguments.search_heuristic
    symtuner.mode = tool

    for i, _ in enumerate(time_budget_handler):
        Run_KLEE(pconfig, pgm, stgy, arguments.total_budget, arguments.core_num,
                 homi_iter, tool, d_name, homi_step, None, str(top_dir),
                 feat_iter, weight_idx)

        dir_name, testcases_homi, homi_rm_cmd = Run_gcov(
            pconfig, pgm, stgy, homi_iter, tool, arguments.core_num,
            homi_data, d_name)
        os.chdir(cur_dir)
        symtuner.add(pconfig, testcases_homi,
                     evaluation_kwargs=evaluation_argument,
                     rm_cmd=homi_rm_cmd,
                     homi_target=pconfig['gcov_path'],
                     flag="basehomi")
        homi_data = symtuner.homidata

        topk_testcases = SetCoverProblem(homi_data, homi_iter)
        features = Feature_Extractor(pgm, stgy, dir_name, topk_testcases,
                                     arguments.core_num, homi_iter, tool)
        feature_data_path, pruning_path = PruningStgy_Generator(
            pconfig, pgm, stgy, arguments.core_num, features, dir_name,
            topk_testcases, homi_iter, tool)
        homi_data_path.append((feature_data_path, pruning_path))

        homi_iter += 1

        rm_dir = " ".join(["rm", "-rf"]) + " " + "/".join([
            str(BASE_DIR / exp_dir),
            tool + "__" + stgy + str(homi_step),
            pgm,
            str(arguments.core_num),
        ])
        os.system(rm_dir)

        homi_step += 1
        os.chdir(cur_dir)

        elapsed = time_budget_handler.elapsed
        coverage, bugs = symtuner.get_coverage_and_bugs()
        allCoverage |= symtuner.allCoverage
        execCount += 1

        get_logger().info(f'Execution Number: {i + 1} '
                          f'Time budget: 120 '
                          f'tool : {tool} '
                          f'Time elapsed: {elapsed} '
                          f'Before Coverage: {len(beforeCoverage)} '
                          f'All Coverage: {len(allCoverage)} '
                          f'execCount : {execCount}')
        beforeCoverage = allCoverage.copy()

        with coverage_csv.open('a') as stream:
            stream.write(f'{elapsed}, {len(allCoverage)}\n')
        with found_bugs_txt.open('w') as stream:
            stream.writelines((f'Testcase: {Path(symtuner.get_testcase_causing_bug(bug)).absolute()} '
                               f'Bug: {bug}\n' for bug in bugs))

        execution_num += 1

    os.chdir(root_dir)

    coverage, bugs = symtuner.get_coverage_and_bugs()
    get_logger().info(f'Standalone HOMI achieved {len(coverage)} coverage.')
