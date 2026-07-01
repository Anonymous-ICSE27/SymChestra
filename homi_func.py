import scipy.stats as stats
import glob, os, sys, argparse, signal
import numpy as np
import json, random
import time, datetime
import subprocess

from copy import deepcopy
from collections import defaultdict
from threading import Timer
from subprocess import Popen, PIPE
from pathlib import Path

from klee import KLEESymTuner
from logger import get_logger
from symtuner import TimeBudgetHandler

BASE_DIR = Path(__file__).resolve().parent

configs = {
    's_dir': str(BASE_DIR),
    'e_dir': str(BASE_DIR / 'symchestra_experiments'),
    'b_dir': str(BASE_DIR / 'klee_feathomi' / 'build')
}

start_time = datetime.datetime.now()

mem_budget=2000 #default memeory budget in KLEE

S_ratio=[20,60,3] # sample space for the pruning ratio.
lower, upper = -1.0, 1.0 #feature weight range

tried_wv = {}
d_tried_budget = {}
d_tc_data = {}


def Discrete_Space(sample_space):
    # Sample Space S = [min_val, max_val, interval].
    # (e.g., [200,800,4] -> [200,400,600,800])
    space = []
    min_val = sample_space[0]
    max_val = sample_space[1]
    interval = sample_space[2]
    space.append(min_val)
    for i in range(1,interval-1):
        val=min_val+int((max_val-min_val)/(interval-1))*i
        space.append(val)
    if min_val == max_val:
        return space
    space.append(max_val)
    return space


def Load_Pgm_Config(config_file):
    with open(config_file, 'r') as f:
        parsed = json.load(f)
    return parsed


def Kill_Process(process):
    # with open(configs['s_dir']+"/killed_history", 'a') as f:
    #     f.write(testcase+"\n")
    os.killpg(os.getpgid(process.pid), signal.SIGTERM)
    print("timeover!")


def Timeout_Checker(total_time, tool):
    current_time = datetime.datetime.now()
    elapsed_time = (current_time-start_time).total_seconds()
    if total_time < elapsed_time:
        os.chdir(configs['s_dir'])
        print ("#############################################")
        print ("################Time Out!!!!!################")
        print ("#############################################")
        sys.exit()

    return elapsed_time

def gen_run_cmd(l_config, pgm, stgy, mem, iters, tool, ith_trial, result_dir, 
                homi_step, iterIndex, featTopDir, feat_iter, weight_idx, parameters=None, flag=None, ram=None):

    symbolic_args = l_config['sym_options']
    pgm_name = l_config.get("pgm_name", pgm)
    if stgy == 'roundrobin' or feat_iter == 0:
        stgy = "random-path --search=nurs:covnew"

    max_time = "120"
    ## .randw
    if feat_iter != 0:
        if flag == "rand":
            stgy = f"auto --feature={featTopDir}/features/{feat_iter}.f --weight={featTopDir}/weight/iteration-{feat_iter}/{weight_idx}.randw"
        else:
            stgy = f"auto --feature={featTopDir}/features/{feat_iter}.f --weight={featTopDir}/weight/iteration-{feat_iter}/{weight_idx}.w"

    if ram:
        klee_build_path = str(BASE_DIR / 'klee_ramhomi' / 'build' / 'bin')
    else:
        klee_build_path = str(BASE_DIR / 'klee_feathomi' / 'build' / 'bin')

    run_cmd = " ".join([f"{klee_build_path}/klee", "-trial=" + str(iters), f"--search={stgy}", f"-max-time={max_time}",
                           "--max-memory="+mem, "--watchdog", 
                           "-dirname=" + configs['e_dir'] + "/" + result_dir, "-write-kqueries", "-only-output-states-covering-new", 
                           "--simplify-sym-indices", "--output-module=false", "--output-source=false", "--output-stats=false", 
                           "--disable-inlining", "--use-forked-solver", "--use-cex-cache", "--libc=uclibc", "--posix-runtime", 
                           "-env-file="+configs['b_dir']+"/../test.env", 
                           "--max-sym-array-size=4096", "--max-solver-time=30", "--switch-type=internal", 
                           "--use-batching-search", "--batch-instructions=10000", "-ignore-solver-failures"])

    if parameters is not None:
        klee_options = []
        sym_arg_options = []
        sym_files_options = []
        sym_stdin_options = []
        sym_stdout_options = []

        space_seperate_keys = ['sym-arg', 'sym-args',
                                'sym-files', 'sym-stdin']
        sym_arg_keys = ['sym-arg', 'sym-args']
        for key, values in parameters.items():
            if "output-dir" in key or 'max-time' in key or 'write-kqueries' in key:
                continue

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

        
        run_cmd = " ".join([f"{klee_build_path}/klee", "-trial=" + str(iters), f"--search={stgy}", f"-max-time={max_time}", "-dirname=" + configs['e_dir'] + "/" + result_dir, "-write-kqueries", *klee_options])

    if iters != 0 and tool == "homi":
        run_cmd = run_cmd + f" -homi -parallel={str(ith_trial)} --iterIndex={iters}"

    if parameters is not None:
        run_cmd = " ".join([run_cmd, f"{pgm_name}.bc", *sym_arg_options, *sym_files_options, *sym_stdin_options, *sym_stdout_options])
    else:
        run_cmd = " ".join([run_cmd, f"{pgm_name}.bc", symbolic_args])
    # run_cmd = run_cmd + " 1>/dev/null 2>/dev/null"
    return run_cmd

def run_all(l_config, pgm, stgy, mem, ith_trial, iters, tool, d_name,
            homi_step, iterIndex, featTopDir, feat_iter, weight_idx, parameters=None, flag=None, ram=None):

    top_dir = "/".join([configs['e_dir'], tool + "__" + stgy + str(iters), pgm])
    if not os.path.exists(top_dir):
        os.makedirs(top_dir)
    
    group_dir = top_dir + "/" + str(ith_trial)

    os.system(" ".join(["cp -r", l_config['pgm_dir'], group_dir]))
    os.chdir(group_dir + l_config['exec_dir'])
    
    result_dir = "result_" + d_name 
    top_tc_dir = "/".join([configs['e_dir'], result_dir])
    if not os.path.exists(top_tc_dir):
        os.mkdir(top_tc_dir)

    if tool == "homi":
        tc_dir = "/".join([configs['e_dir'], result_dir, str(ith_trial) + "_" + pgm + "_tc_dir"])
    else:
        tc_dir = "/".join([configs['e_dir'], result_dir, str(ith_trial) + f"{tool}_" + pgm + "_" + stgy + "_tc_dir"])
    
    if not os.path.exists(tc_dir):
        os.mkdir(tc_dir)
    
    os.chdir(group_dir + l_config['exec_dir'])
    run_cmd = gen_run_cmd(l_config, pgm, stgy, mem, iters, tool, ith_trial, result_dir, 
                          homi_step, iterIndex, featTopDir, feat_iter, weight_idx, parameters=parameters, flag=flag, ram=ram)
    
    print("RR : ", run_cmd)
    with open(os.devnull, 'wb') as devnull:
        os.system(run_cmd)

    klee_dir = "klee-out-0"
    rm_cmd=" ".join(["rm", klee_dir+"/assembly.ll", klee_dir+"/run.istats"])
    os.system(rm_cmd) 

    mv_cmd = " ".join(["mv", klee_dir, tc_dir + "/" + str(iters) + "__tc_dirs"]) 
    print(mv_cmd)
    os.system(mv_cmd)

    mv2_cmd = " ".join(["mv", "time_result state_data", tc_dir + "/" + str(iters) + "__tc_dirs/"]) 
    os.system(mv2_cmd)

    return group_dir + l_config['exec_dir']

def Run_KLEE(load_config, pgm, stgy, 
             total_time, ith_trial, iters, tool, d_name, 
             homi_step, iterIndex, top_dir, feat_iter, weight_idx, parameters=None, flag=None, ram=None):
    # Check whether the total time budget expires.
    elapsed_time = Timeout_Checker(total_time, tool)
    
    # Maintain the number of each tried small budget.
    os.chdir(configs['s_dir'])
    remain_time = int(total_time-elapsed_time)
    output_dir = run_all(load_config, pgm, stgy, str(mem_budget), ith_trial, int(iters), tool, d_name, 
                         homi_step, iterIndex, top_dir, feat_iter, weight_idx, parameters=parameters, flag=flag, ram=ram)
    return output_dir
    
def Run_gcov(load_config, pgm, stgy, iters, tool, ith_trial, Data, d_name):
    result_dir = "result_" + d_name 
    if tool == "homi":
        dir_name = "/".join([result_dir, ith_trial + "_" + pgm + "_tc_dir"])
    else:
        dir_name = "/".join([result_dir, ith_trial + tool + "_" + pgm + "_" + stgy + "_tc_dir"])

    os.chdir(configs['e_dir'] + "/" + dir_name + "/" + str(iters) + "__tc_dirs")

    # print(os.getcwd(), os.listdir(os.getcwd()))
    testcases = [os.getcwd() + "/" + x for x in os.listdir(os.getcwd()) if "ktest" in x]
    testcases.sort(key=lambda x:float((x.split('.')[0]).split('test')[1]))       
        
    early_testcases = [os.getcwd() + "/" + x for x in os.listdir(os.getcwd()) if "early" in x]
    early_testcases.sort(key=lambda x:float((x.split('.')[0]).split('test')[1]))       

    # Maintains a quadruple of information used to generate each test-case tc.
    # tc -> [time_budget, pruning_ratio, rfeat_list, weight_vector]
    if iters != 0:
        with open('info', 'r') as f:
            lines = f.readlines()

            if len(lines) != 0:
                args = lines[0].split()
                
                for arg in args:
                    if "-max-time" in arg:
                        budget = int(arg.split('=')[1])

        for e_tc in early_testcases:
            with open(e_tc, 'r') as f:
                lines = f.readlines()
                rfeat_data = lines[0]
                
                if "rfeats: " in rfeat_data:
                    l_rfeats = (rfeat_data.split('rfeats: ')[1]).split()
                    l_rfeats = list(map(lambda s: int(s.strip()), l_rfeats))

                    pratio_data = lines[1]
                    pratio = str(int(pratio_data.split('pratio: ')[1]))
                        
                    wvector_data=lines[2]
                    wvector = (wvector_data.split('wvector: ')[1].split('\n'))[0]
                        
                    tc = str(iters) + "__tc_dirs/" + e_tc.split('/')[-1].split('early')[0] + "ktest"

                    d_tc_data[tc] = [budget, pratio, l_rfeats, wvector]
        
        flag = 0

        for tc in testcases:
            tc = str(iters) + "__tc_dirs/" + tc.split('/')[-1]
            
            if tc in d_tc_data.keys():
                recent_data = d_tc_data[tc]
                flag=1
            
            elif tc not in d_tc_data.keys() and flag==1:
                d_tc_data[tc] = recent_data
            
            else:
                continue

    os.chdir(load_config['gcov_path'])
    rm_cmd = " ".join(["rm", load_config['gcov_file'], load_config['gcda_file']])
    
    return dir_name, testcases, rm_cmd


def SetCoverProblem(Data, iters):
    temp_Data = deepcopy(Data)
    topk_testcases = []
    intersect_set = set()
    
    total_size = len(temp_Data)
    
    # greedy algorithm for solving the set cover problem. 
    for i in range(1, total_size + 1):
        sorted_list = sorted(temp_Data.items(), key=lambda kv:(len(kv[1])), reverse = True)
        topk_tc = sorted_list[0][0]
        topk_covset = sorted_list[0][1]

        if len(topk_covset) > 0: 
            topk_testcases.append(topk_tc)
            intersect_set = intersect_set | topk_covset 
            for tc in temp_Data.keys():
                temp_Data[tc] = temp_Data[tc] - intersect_set
        else:
            break
    
    return topk_testcases


def Feature_Extractor(pgm, stgy, dir_name, topk_testcases, ith_trial, iters, tool):
    os.chdir(configs['e_dir'] + "/" + dir_name)
    feat_set = set()
    
    Symbolic_arg = "arg"
    Nonsymbolic_arg = "const_arr"
    Eq_expr = "Eq"
    Neq_expr = "false"
    
    for tc in topk_testcases:
        kquery = tc.split('ktest')[0] + "kquery"
        
        if os.path.exists(kquery):
            with open(kquery, 'r') as f:
                query_command_flag = 0
                queries = f.readlines()
                
                for query in queries:    
                    if "query" in query:
                        query_command_flag = 1
                    
                    if query_command_flag == 1:
                        if ((Eq_expr in query) and (Symbolic_arg in query)
                            and (Neq_expr not in query) and (Nonsymbolic_arg not in query)):

                            feature = query.split('\n')[0]
                            
                            if (len(feat_set) < 200):
                                feat_set.add(feature)
                            
                            else:
                                break

    return feat_set


def PruningStgy_Generator(load_config, pgm, stgy, ith_trial, features, dir_name, topk_testcases, iters, tool):
    os.chdir(configs['e_dir'] + "/" + dir_name)
    
    Space_ratio = Discrete_Space(S_ratio)
    
    # "wv_dir" is a set of pruning strategies (= weight vectors).
    wv_dir = "weights/" 
    if not os.path.exists(wv_dir):
        os.mkdir(wv_dir)
    
    wv_t_dir = "weights/" + str(iters + 1) + "trials/" 
    if not os.path.exists(wv_t_dir):
        os.mkdir(wv_t_dir)
     
    feature_data_path = wv_dir + "/" + str(iters + 1) + "feature_data"
    pruning_path = wv_dir + "/" + str(iters + 1) + "pruning_ratio"

    with open(feature_data_path, 'w') as f:
        for feat in features:
            f.write(feat + "\n")  
    
    if iters != 0:
        for wnum in range(1, 51):
            key = str(iters) + "trials" + "/" + str(wnum)+".w"
            with open(wv_dir + "/" + key, 'r') as f:
                lines = f.readlines()
                current_wv = []
                for line in lines:
                    current_wv.append(line.split('\n')[0])
                tried_wv[key] = current_wv

    exploit_decisions = ["exploit", "reverse_exploit", "explore"]
    Prob_exploit = [1, 1, 1] # set the same probablity for the three sampling methods
    policy= (random.choices(exploit_decisions, Prob_exploit))[0]
    
    d_prune_ratio = {}
    d_prune_time = {}
    d_budget = {}
    
    file_name = ith_trial + tool + "_" + pgm + "_" + stgy + "_"
    pruning_ratio = []
    budget_probability = []
    
    # Sample the weight vector, time budget, and purning ratio via Exploration.
    # Use only the exploration method 10 times to collect the enough data.
    if iters < 10 or policy == "explore": 
        policy = "explore"
        # Randomly generate a set of pruning-strategies.
        for wv_id in range(1, 51):
            fname = wv_t_dir  + str(wv_id) + ".w"
            weights = [str(random.uniform(lower, upper)) for _ in range(len(features))] 
            with open(fname, 'w') as f:
                for w in weights:
                    f.write(str(w) + "\n")
        
        # Randomly generate the time budget and pruning_ratio.
        with open (pruning_path, 'w') as f:
            for i in range(0, 51):
                ratio = random.choice(Space_ratio)
                f.write(str(ratio)+"\n") 

    # Sample the weight vector, time budget, and purning ratio via Exploitation or Reverse Exploitation.
    else:
        # Collect the learning data. 
        # Learning data: (1). each feature and the weight value, (2) time budget, (3). pruning-ratio)
        d_feat_wvs = {}
        for tc in topk_testcases:
            trial_num = int(tc.split('__tc_dirs')[0].split('/')[-1])

            if (tc in d_tc_data.keys()) and (trial_num !=0):
                budget = d_tc_data[tc][0]
                pratio = d_tc_data[tc][1]
                l_rfeats = d_tc_data[tc][2] 
                wvector = d_tc_data[tc][3] 

                feats = wv_dir + str(trial_num) + "feature_data"
                feats_list = []

                with open(feats, 'r') as ft:
                    feats_list = ft.readlines()
                    feats_list = list(map(lambda s: s.strip(), feats_list))
                
                wv_list = tried_wv[wvector]
                
                for idx in range(0, len(feats_list)):
                    if idx not in l_rfeats:
                        feature = feats_list[idx]
                        weight = float(wv_list[idx])

                        if feature in d_feat_wvs.keys():
                            d_feat_wvs[feature].append(weight)
                        
                        else:
                            d_feat_wvs[feature] = [weight]
 
        # Sample the weight vector via Exploitation.
        if (policy == "exploit"):
            for wnum in range(1, 51):
                fname = wv_t_dir  + str(wnum) + ".w"
                weights = []
                for feature in features:
                    if feature in d_feat_wvs.keys():
                        mu = np.mean(d_feat_wvs[feature])
                        sigma = np.std(d_feat_wvs[feature])
                        set_size = len(set(d_feat_wvs[feature]))

                        if sigma == 0 or set_size == 1:
                            sigma = 1
                            x = stats.truncnorm((lower - mu) / sigma, (upper - mu) / sigma, loc=mu, scale=sigma)
                        else:
                            x = stats.truncnorm((lower - mu) / sigma, (upper - mu) / sigma, loc=mu, scale=sigma)
                        w = x.rvs(1)[0]
                    else:
                        w = random.uniform(lower, upper)
                    weights.append(w)

                with open(fname, 'w') as f:
                    for w in weights:
                        f.write(str(w) + "\n")
        
        # Sample the weight vector via Reverse_Exploitation.
        else:
            for wnum in range(1,51):
                fname = wv_t_dir  + str(wnum) + ".w"
                weights = []
                for feature in features:
                    if feature in d_feat_wvs.keys():
                        mu = np.mean(d_feat_wvs[feature])
                        sigma = np.std(d_feat_wvs[feature])
                        set_size= len(set(d_feat_wvs[feature]))

                        if sigma == 0 or set_size == 1:
                            sigma = 1
                            x = stats.truncnorm((lower - mu) / sigma, (upper - mu) / sigma, loc=mu, scale=sigma)
                        else:
                            x = stats.truncnorm((lower - mu) / sigma, (upper - mu) / sigma, loc=mu, scale=sigma)
                        w = x.rvs(1)[0]
                    
                        cand_w_list = list(np.random.uniform(lower, upper, 20))
                        contrary_w = 0
                        diff = 0
                    
                        for cand_w in cand_w_list:
                            if abs(cand_w - w) > diff:
                                diff = abs(cand_w -w)
                                contrary_w=cand_w
                        w = contrary_w
                    
                    else:
                        w = random.uniform(lower, upper)
                    weights.append(w)

                with open(fname, 'w') as f:
                    for w in weights:
                        f.write(str(w) + "\n")

        # Sample the pruning ratio.
        pratio_probability = []
        for r in Space_ratio:
            r = str(r)
            if r in d_prune_ratio.keys():
                pratio_probability.append(d_prune_ratio[r])
            else:
                pratio_probability.append(1)

        with open (pruning_path, 'w') as f:
            for i in range(0 ,51):
                ratio = (random.choices(Space_ratio, pratio_probability))[0]
                f.write(str(ratio) +"\n") 
        

    with open('topk_tcs_data', 'a') as f:
        f.write(str(iters + 1) + "-> topk-tcs: " + str(len(topk_testcases))+")\n")
        f.write("policy: " + policy+"\n")
        f.write("ratio: " + str(d_prune_ratio)+"\n")
        f.write("budget: " + str(d_budget)+"\n")
        f.write("tried_budget_counter: " + str(d_tried_budget)+"\n")
        f.write("budget_prob: " + str(budget_probability)+"\n")

    return feature_data_path, pruning_path


def PruningStgy_Generator_Random(load_config, pgm, stgy, ith_trial, features, dir_name, topk_testcases, iters, tool):
    os.chdir(configs['e_dir'] + "/" + dir_name)
    
    Space_ratio = Discrete_Space(S_ratio)
    
    # "wv_dir" is a set of pruning strategies (= weight vectors).
    wv_dir = "weights/" 
    if not os.path.exists(wv_dir):
        os.mkdir(wv_dir)
    
    wv_t_dir = "weights/" + str(iters + 1) + "trials/" 
    if not os.path.exists(wv_t_dir):
        os.mkdir(wv_t_dir)
     
    feature_data_path = wv_dir + "/" + str(iters + 1) + "feature_data"
    pruning_path = wv_dir + "/" + str(iters + 1) + "pruning_ratio"

    with open(feature_data_path, 'w') as f:
        for feat in features:
            f.write(feat + "\n")  
    
    if iters != 0:
        for wnum in range(1, 51):
            key = str(iters) + "trials" + "/" + str(wnum)+".w"
            with open(wv_dir + "/" + key, 'r') as f:
                lines = f.readlines()
                current_wv = []
                for line in lines:
                    current_wv.append(line.split('\n')[0])
                tried_wv[key] = current_wv

    policy = "explore"
    
    d_prune_ratio = {}
    d_prune_time = {}
    d_budget = {}
    
    file_name = ith_trial + tool + "_" + pgm + "_" + stgy + "_"
    pruning_ratio = []
    budget_probability = []
    
    # Sample the weight vector, time budget, and purning ratio via Exploration.
    # Use only the exploration method 10 times to collect the enough data.
    if iters < 10 or policy == "explore": 
        policy = "explore"
        # Randomly generate a set of pruning-strategies.
        for wv_id in range(1, 51):
            fname = wv_t_dir  + str(wv_id) + ".w"
            weights = [str(random.uniform(lower, upper)) for _ in range(len(features))] 
            with open(fname, 'w') as f:
                for w in weights:
                    f.write(str(w) + "\n")
        
        # Randomly generate the time budget and pruning_ratio.
        with open (pruning_path, 'w') as f:
            for i in range(0, 51):
                ratio = random.choice(Space_ratio)
                f.write(str(ratio) + "\n") 

    # Sample the weight vector, time budget, and purning ratio via Exploitation or Reverse Exploitation.
    else:
        # Collect the learning data. 
        # Learning data: (1). each feature and the weight value, (2) time budget, (3). pruning-ratio)
        d_feat_wvs = {}
        for tc in topk_testcases:
            trial_num = int(tc.split('__tc_dirs')[0].split('/')[-1])

            if (tc in d_tc_data.keys()) and (trial_num !=0):
                budget = d_tc_data[tc][0]
                pratio = d_tc_data[tc][1]
                l_rfeats = d_tc_data[tc][2] 
                wvector = d_tc_data[tc][3] 

                feats = wv_dir + str(trial_num) + "feature_data"
                feats_list = []

                with open(feats, 'r') as ft:
                    feats_list = ft.readlines()
                    feats_list = list(map(lambda s: s.strip(), feats_list))
                
                wv_list = tried_wv[wvector]
                
                for idx in range(0, len(feats_list)):
                    if idx not in l_rfeats:
                        feature = feats_list[idx]
                        weight = float(wv_list[idx])

                        if feature in d_feat_wvs.keys():
                            d_feat_wvs[feature].append(weight)
                        
                        else:
                            d_feat_wvs[feature] = [weight]
 
        # Sample the weight vector via Exploitation.
        if (policy == "exploit"):
            for wnum in range(1, 51):
                fname = wv_t_dir  + str(wnum) + ".w"
                weights = []
                for feature in features:
                    if feature in d_feat_wvs.keys():
                        mu = np.mean(d_feat_wvs[feature])
                        sigma = np.std(d_feat_wvs[feature])
                        set_size = len(set(d_feat_wvs[feature]))

                        if sigma == 0 or set_size == 1:
                            sigma = 1
                            x = stats.truncnorm((lower - mu) / sigma, (upper - mu) / sigma, loc=mu, scale=sigma)
                        else:
                            x = stats.truncnorm((lower - mu) / sigma, (upper - mu) / sigma, loc=mu, scale=sigma)
                        w = x.rvs(1)[0]
                    else:
                        w = random.uniform(lower, upper)
                    weights.append(w)

                with open(fname, 'w') as f:
                    for w in weights:
                        f.write(str(w) + "\n")
        
        # Sample the weight vector via Reverse_Exploitation.
        else:
            for wnum in range(1,51):
                fname = wv_t_dir  + str(wnum) + ".w"
                weights = []
                for feature in features:
                    if feature in d_feat_wvs.keys():
                        mu = np.mean(d_feat_wvs[feature])
                        sigma = np.std(d_feat_wvs[feature])
                        set_size= len(set(d_feat_wvs[feature]))

                        if sigma == 0 or set_size == 1:
                            sigma = 1
                            x = stats.truncnorm((lower - mu) / sigma, (upper - mu) / sigma, loc=mu, scale=sigma)
                        else:
                            x = stats.truncnorm((lower - mu) / sigma, (upper - mu) / sigma, loc=mu, scale=sigma)
                        w = x.rvs(1)[0]
                    
                        cand_w_list = list(np.random.uniform(lower, upper, 20))
                        contrary_w = 0
                        diff = 0
                    
                        for cand_w in cand_w_list:
                            if abs(cand_w - w) > diff:
                                diff = abs(cand_w -w)
                                contrary_w=cand_w
                        w = contrary_w
                    
                    else:
                        w = random.uniform(lower, upper)
                    weights.append(w)

                with open(fname, 'w') as f:
                    for w in weights:
                        f.write(str(w) + "\n")

        # Sample the pruning ratio.
        pratio_probability = []
        for r in Space_ratio:
            r = str(r)
            if r in d_prune_ratio.keys():
                pratio_probability.append(d_prune_ratio[r])
            else:
                pratio_probability.append(1)

        with open (pruning_path, 'w') as f:
            for i in range(0 ,51):
                ratio = (random.choices(Space_ratio, pratio_probability))[0]
                f.write(str(ratio) +"\n") 
        

    with open('topk_tcs_data', 'a') as f:
        f.write(str(iters + 1) + "-> topk-tcs: " + str(len(topk_testcases))+")\n")
        f.write("policy: " + policy+"\n")
        f.write("ratio: " + str(d_prune_ratio)+"\n")
        f.write("budget: " + str(d_budget)+"\n")
        f.write("tried_budget_counter: " + str(d_tried_budget)+"\n")
        f.write("budget_prob: " + str(budget_probability)+"\n")

    return feature_data_path, pruning_path
