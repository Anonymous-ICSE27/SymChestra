from multiprocessing import Process, Manager, Queue
import subprocess
import os
import time
import pickle

def branch_handler(ktest_gcov):
    with open(ktest_gcov, 'r', errors='ignore') as f:
        lines = f.read().split('        -:    0:Source')[1:]
    covered_branch = set()
    for s in lines:
        s = s.split('\n')
        src_name = s[0].split('/')[-1]
        line_number = 0
        code_line_start = 1
        while "0:" in s[code_line_start]: code_line_start += 1
       
        for l in s[code_line_start:]:
            if ":" in l:
                line_number += 1
                continue                 
            if 'taken' in l:
                tmp = l.split()
                if tmp[3] != '0%':
                    covered_branch.add(f"{src_name}_{line_number}_{tmp[1]}")
    # os.system(f"rm {ktest_gcov}")
    return covered_branch

class data_generator:
    def __init__(self, pconfig, top_dir, options):
        self.pconfig = pconfig
        self.pgm = pconfig["pgm_name"]
        self.top_dir = top_dir
        self.n_weights = options.n_scores
        self.gcda_list = os.popen(f'find {os.path.abspath(self.pconfig["gcov_path"])} -name "*.gcno"').read().replace('\n',' ').replace("gcno", "gcda")
        self.gcov_dir = f"/root/symchestra/symtuner/{self.pconfig['gcov_path']}/{self.pconfig['exec_dir']}"
        self.bin_dir = os.path.abspath('klee_featmaker/build/bin')
        self.gcda_file = self.pconfig["gcda_file"]
        self.gcov_file = self.pconfig["gcov_file"]

        self.potential_errors_list = []
    
    def run_replay(self, iteration, widx, potential_errors, flag=False):
        ktest_lst = os.popen(f"ls {self.top_dir}/result/iteration-{iteration}/{widx}/*.ktest 2>/dev/null").read().split()
        os.chdir(self.gcov_dir)
        covered_branches = {}
        coverage = set()
        for ktest in ktest_lst:
            process = subprocess.Popen(f"{self.bin_dir}/klee-replay ./{self.pgm} {ktest}", stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=True)
            try:
                _, stderr = process.communicate(timeout=0.1)
                if "CRASHED" in stderr.decode(errors='ignore'):
                    potential_errors.append(ktest)
            except subprocess.TimeoutExpired:
                pass
                process.kill()
        
            os.system(f"gcov -b {self.gcda_list} 1>/dev/null 2>/dev/null; cat *.gcov>{ktest}_gcov 2>/dev/null; rm -f {self.gcda_list} *.gcov 2>/dev/null")
            covered_branches[ktest] = branch_handler(f"{ktest}_gcov")
            rm_rf_cmd = " ".join(["rm", "-rf", f"{ktest}_gcov"])
            os.system(rm_rmf_cmd)
            coverage |= covered_branches[ktest]
            process.kill()
        os.chdir(self.top_dir)

        if not flag:
            with open(f"{self.top_dir}/{widx}_result.pkl", 'wb') as f:
                pickle.dump(covered_branches, f)

        return coverage

    def generate_data(self, iteration, 
                      seedingMode = False, windex = 0):

        if seedingMode:
            potential_errors = []
            coverage = self.run_replay(iteration, windex, potential_errors)

            for each in potential_errors:
                self.potential_errors_list.append(each)

            with open(f"{self.top_dir}/errors/{iteration}_potential_errors{windex}.pkl", 'wb') as f:
                pickle.dump(potential_errors, f)

            return coverage
        else:
            potential_errors = []
            for widx in range(self.n_weights):
                self.run_replay(iteration, widx, potential_errors)
                
            with open(f"{self.top_dir}/errors/{iteration}_potential_errors.pkl", 'wb') as f:
                pickle.dump(potential_errors, f)

    def potential_error_logging(self, iteration):
        for widx in range(self.n_weights):
            rm_cmd = " ".join(["rm", "-rf", f"{self.top_dir}/errors/{iteration}_potential_errors{widx}.pkl"])
            os.system(rm_cmd)

        with open(f"{self.top_dir}/errors/{iteration}_potential_errors.pkl", 'wb') as f:
            pickle.dump(self.potential_errors_list, f)

    def get_iteration_branch_coverage(self, iteration, windex=0):
        return self.run_replay(iteration, windex, [], True)