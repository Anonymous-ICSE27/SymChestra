import os
import time
import random
import glob
import numpy as np
import subprocess as sp
from pathlib import Path

configs = {
	'root_dir': os.path.abspath(os.getcwd()),
    'klee_build_dir': '/root/symchestra/klee_featmaker/build/',
    'klee_build_ram_dir': '/root/symchestra/klee_ram/build/',
    'e_dir': os.path.abspath('../experiments/'), # experiment dir
    'b_dir': os.path.abspath('../klee_feathomi/build/') # build dir
}

search_options = {
    "batching" : "--use-batching-search --batch-instructions=10000",
    "branching" : "--use-branching-search",
}

class klee_executor:
    def __init__(self, pconfig, top_dir, options, coreNum=None, mode="featmaker", symtuner=None, wg=None, log=None):
        self.pconfig = pconfig
        self.pgm = pconfig["pgm_name"]
        self.top_dir = top_dir
        self.n_scores = options.n_scores
        self.main_option = options.main_option
        self.total_budget = options.total_budget
        self.feat_len = 0
        self.bin_dir = '/root/symchestra/klee_featmaker/build/bin'
        self.bin_ram_dir = '/root/symchestra/klee_ram/build/bin'
        self.bin_homi_dir = '/root/symchestra/klee_feathomi/build/bin'
        self.bin_homiram_dir = '/root/symchestra/klee_ramhomi/build/bin'
        self.llvm_dir = f"{self.top_dir}/obj-llvm/{self.pconfig['exec_dir']}"

        self.symtuner = symtuner
        self.exploration_steps = options.exploration_steps
        self.wg = wg
        self.log = log

        self.mode = mode
        self.coreNum = str(coreNum)

    def stgy_handler(self, top_dir, iteration, weight_idx, flag2=None):
        if iteration <= 0 or weight_idx is None:
            return "random-path --search=nurs:covnew"
        return f"auto --feature={top_dir}/features/{iteration}.f --weight={top_dir}/weight/iteration-{iteration}/{weight_idx}.w"

    def execute_klee(self, iteration=None, parameters=None, weight_idx=None, get_logger=None, 
                     homiinfo=None, flag=None, data=None, mode=None, flag2=None, ram=None, 
                     seed=None, badQueries=None, separate=None):
        os.chdir(self.llvm_dir)

        target = self.llvm_dir + "/" + self.pgm + ".bc"
        output_dir = parameters['-output-dir']
        max_time = parameters['-max-time']

        search_key = "batching"
        if self.pgm in ["find", "sqlite3"]:
            search_key = "branching"

        print(flag, mode, separate, weight_idx)
        if flag == "featmaker" or flag == "basefeatmaker" or (mode == "featmaker" and separate):
            search_stgy = self.stgy_handler(self.top_dir, iteration, weight_idx, flag2=flag2)
            symbolic_args = self.pconfig['sym_options']
            
            if ram:
                klee_cmd = self.bin_ram_dir + "/klee -use-sym-addr -merge-objects"
                if homiinfo is not None:
                    klee_cmd = self.bin_homiram_dir + "/klee -use-sym-addr -merge-objects"
            else:
                klee_cmd = self.bin_dir + "/klee"
                if homiinfo is not None:
                    klee_cmd = self.bin_homi_dir + "/klee"

            cmd = " ".join([klee_cmd, 
                                "-only-output-states-covering-new", "--simplify-sym-indices", "--output-module=false",
                                "--output-source=false", "--output-stats=false", "--disable-inlining", "--write-kqueries", 
                                "--use-forked-solver", "--use-cex-cache", "--libc=uclibc", "--ignore-solver-failures",
                                "--posix-runtime", f"-env-file={configs['klee_build_dir']}/../test.env",
                                "--max-sym-array-size=4096", "--max-memory-inhibit=false",
                                "--switch-type=internal", search_options[search_key], 
                                f"--watchdog -max-time={max_time} --search={search_stgy} --output-dir={output_dir}"])


            if homiinfo is not None:
                cmd = " ".join([cmd, f"-dirname=" + configs['e_dir'] + "/result_All", "-symmode=mode", f"-parallel={self.coreNum} -trial={homiinfo} --iterIndex={homiinfo}"])

            if seed is not None:
                for eachseed in seed:
                    cmd = " ".join([cmd, f"--seed-file={eachseed}"])
                
                if badQueries is not None:
                    for each_kquery in badQueries:
                        cmd = " ".join([cmd, f"--kquery-file={each_kquery}"])
                    
                cmd = " ".join([cmd, target, symbolic_args])
            else:
                cmd = " ".join([cmd, target, symbolic_args])
        else:
            klee_options = []
            sym_arg_options = []
            sym_files_options = []
            sym_stdin_options = []
            sym_stdout_options = []

            space_seperate_keys = ['sym-arg', 'sym-args',
                                    'sym-files', 'sym-stdin']
            sym_arg_keys = ['sym-arg', 'sym-args']
            for key, values in parameters.items():
                stripped_key = key.strip('-').split()[0]
                if not isinstance(values, list):
                    values = [values]
                for value in values:
                    if value is None:
                        param = key
                    elif stripped_key in space_seperate_keys:
                        param = f'{key} {value}'
                    elif stripped_key == 'sym-stdout':
                        if value == 'off':
                            continue
                        param = key
                    else:
                        param = f'{key}={value}'
                    if stripped_key in sym_arg_keys:
                        sym_arg_options.append(param)
                    elif stripped_key == 'sym-files':
                        sym_files_options.append(param)
                    elif stripped_key == 'sym-stdin':
                        sym_stdin_options.append(param)
                    elif stripped_key == 'sym-stdout':
                        sym_stdout_options.append(param)
                    else:
                        klee_options.append(param)

            if flag == "symtuner":
                search_stgy = self.stgy_handler(self.top_dir, iteration, weight_idx, flag2=flag2)
            else:
                search_stgy = self.stgy_handler(self.top_dir, iteration, weight_idx, flag2=flag2)

            if ram:
                klee_cmd = self.bin_ram_dir + "/klee -use-sym-addr -merge-objects"
            else:
                klee_cmd = self.bin_dir + "/klee"

            cmd = ' '.join([klee_cmd, f"--search={search_stgy}", *klee_options])

            if seed is not None:
                for eachseed in seed:
                    cmd = " ".join([cmd, f"--seed-file={eachseed}"])
                
                if badQueries is not None:
                    for each_kquery in badQueries:
                        cmd = " ".join([cmd, f"--kquery-file={each_kquery}"])

                cmd = ' '.join([cmd, str(target), *sym_arg_options, *sym_files_options, *sym_stdin_options, *sym_stdout_options])
            else:
                cmd = ' '.join([cmd, str(target), *sym_arg_options, *sym_files_options, *sym_stdin_options, *sym_stdout_options])
            
        # Run KLEE
        get_logger().info(f'klee command: {cmd}')
        get_logger().debug(f'klee command: {cmd}')
        try:
            _ = sp.run(cmd, stdout=sp.PIPE, stderr=sp.PIPE,
                       shell=True, check=True)
        except sp.CalledProcessError as e:
            stderr = e.stderr.decode(errors='replace')
            lastline = stderr.strip().splitlines()[-1]
            if 'KLEE' in lastline and 'kill(9)' in lastline:
                get_logger().warning(f'KLEE process kill(9)ed. Failed to terminate nicely.')
            else:
                log_file = Path(f"{output_dir}/symtuner.log")
                get_logger().warning(f'Fail({e.returncode})ed to execute KLEE. '
                                     f'See for more details: {log_file}')
                with log_file.open('w', encoding='UTF-8') as f:
                    f.write(f'command: {cmd}\n')
                    f.write(f'return code: {e.returncode}\n')
                    f.write('\n')
                    f.write('-- stdout --\n')
                    stdout = e.stdout.decode(errors='replace')
                    f.write(f'{stdout}\n')
                    f.write('-- stderr --\n')
                    stderr = e.stderr.decode(errors='replace')
                    f.write(f'{stderr}\n')

        testcases = [output_dir + "/" + x for x in os.listdir(output_dir) if "ktest" in x]
        return testcases