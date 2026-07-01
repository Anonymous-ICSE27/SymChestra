import os
import copy
import random
import numpy as np
import pickle
import re

largeValRe = None
lv_hp = 8

def abstract_condition(lines):
    result = set()
    largeValRe = re.compile("\\d{"+str(lv_hp)+",}")
    for line in lines:
        result.add(re.sub(largeValRe, "LargeValue", line))        
    return result

def get_pc_naive(ktest_list):
    local_query_set = set()
    for ktest in ktest_list:
        kquery = ktest.split('.')[0] + '.kquery'
        if not os.path.exists(kquery):
            continue
        with open(kquery, 'r', errors='ignore') as f:
            lines = f.read().split('(query [\n') 
        lines = lines[1].split('\n')[:-2]
        local_query_set |= set(lines)
    return local_query_set

def get_pc(ktest):
    suffix = ktest.split('.')[-1]
    new_suffix = suffix.replace('ktest', 'kquery')
    kquery = ktest.split('.')[0] + f'.{new_suffix}'
    if not os.path.exists(kquery):
        return []
    with open(kquery, 'r', errors='ignore') as f:
        lines = f.read().split('(query [\n')
    lines = lines[1].split('\n')[:-2]
    return lines

class feature_generator:
    def __init__(self, data, top_dir, options, mode=None):
        self.data = data
        self.top_dir = top_dir
        self.n_scores = options.n_scores
        self.main_option = options.main_option
        self.mode = mode

        self.tempFMFeat = set()
        self.tempHomiFeat = set()

    def collect_naive(self, iteration, featmakerdata):
        if iteration <= 1:
            self.data["bsidx_clusters"] = {}
            self.data["unique branchset"] = []
            self.data["branches"] = set()
            self.data["plot data"] = []
        
        self.data["coverage"] = []

        for widx in range(self.n_scores):
            tmp_covered_set = set()
            for ktest, bs in featmakerdata[widx].items():
                if bs not in self.data["unique branchset"]:
                    self.data["unique branchset"].append(bs)

                    self.data["bsidx_clusters"][len(self.data["unique branchset"]) - 1] = []
                bsidx = self.data["unique branchset"].index(bs)
                self.data["bsidx_clusters"][bsidx].append(ktest)
                tmp_covered_set |= bs
            self.data["coverage"].append(tmp_covered_set)
            self.data["branches"] |= tmp_covered_set
        self.data["plot data"].append(len(self.data["branches"]))
        # with open(f"{self.top_dir}/data/{iteration}.pkl", 'wb') as f:
        #     pickle.dump(self.data, f)

    def collect_featmaker(self, iteration, featmakerdata):
        if iteration <= 1:
            self.data["bsidx_clusters"] = {}
            self.data["unique branchset"] = []
            self.data["unique pc"] = []
            self.data["branches"] = set()
            self.data["plot data"] = []
            self.data["pre_covered"] = set()

        self.data["widx_info"] = np.zeros((self.n_scores,2))
        self.data["widx_pcidxes"] = {}
        tmp_covered_set = set()
        for widx in range(self.n_scores):
            trial_branches = set()
            self.data["widx_pcidxes"][widx] = set()
            
            for ktest, bs in featmakerdata[widx].items():
                tmp_pc = get_pc(ktest)

                if len(tmp_pc) == 0:
                    continue
                
                if bs not in self.data["unique branchset"]:
                    self.data["unique branchset"].append(bs)
                    self.data["bsidx_clusters"][len(self.data["unique branchset"]) - 1] = set()
                
                if tmp_pc not in self.data["unique pc"]:
                    self.data["unique pc"].append(tmp_pc)

                bsidx = self.data["unique branchset"].index(bs)
                
                pcidx = self.data["unique pc"].index(tmp_pc)
                self.data["widx_pcidxes"][widx].add(pcidx)

                self.data["bsidx_clusters"][bsidx].add(pcidx)
                trial_branches |= bs

            if iteration != 1:
                self.data["widx_info"][widx] = np.array([len(trial_branches - self.data["pre_covered"]), len(trial_branches)])
            tmp_covered_set |= trial_branches
        
        self.data["branches"] |= tmp_covered_set
        self.data["pre_covered"] = set()
        self.data["pre_covered"] |= tmp_covered_set
        self.data["plot data"].append(len(self.data["branches"]))

    def collect_featmaker_homi(self, iteration, homidata):
        if iteration <= 1:
            self.data["bsidx_clusters"] = {}
            self.data["unique branchset"] = []
            self.data["unique pc"] = []
            self.data["branches"] = set()
            self.data["plot data"] = []
            self.data["pre_covered"] = set()

        tmp_covered_set = set()
        # for widx in range(self.n_scores):
        trial_branches = set()
        
        for ktest, bs in homidata.items():
            tmp_pc = get_pc(ktest)

            if len(tmp_pc) == 0:
                continue
            
            if bs not in self.data["unique branchset"]:
                self.data["unique branchset"].append(bs)
                self.data["bsidx_clusters"][len(self.data["unique branchset"]) - 1] = set()
            
            if tmp_pc not in self.data["unique pc"]:
                self.data["unique pc"].append(tmp_pc)

            bsidx = self.data["unique branchset"].index(bs)
            
            pcidx = self.data["unique pc"].index(tmp_pc)

            self.data["bsidx_clusters"][bsidx].add(pcidx)
            trial_branches |= bs

        tmp_covered_set |= trial_branches
        
        self.data["branches"] |= tmp_covered_set
        self.data["pre_covered"] = set()
        self.data["pre_covered"] |= tmp_covered_set
        self.data["plot data"].append(len(self.data["branches"]))

    def collect(self, iteration, featmakerdata=None):
        if self.main_option == "featmaker":
            self.collect_featmaker(iteration, featmakerdata)
        else:
            self.collect_naive(iteration, featmakerdata)

        print(f"\tBranch Coverage in iteration-{iteration-1} : {self.data['plot data'][-1]}")

    def collect_homi(self, iteration, homidata=None):
        self.collect_featmaker_homi(iteration, homidata)

    def cluster_setcover(self):
        bs_br_matrix = np.full((len(self.data["unique branchset"]), len(self.data["branches"])), False)
        coverage_list = np.array([len(x) for x in self.data["unique branchset"]])
        br_dict = {}

        for br in self.data["branches"]:
            br_dict[br] = len(br_dict)
        for bsidx, bs in enumerate(self.data["unique branchset"]):
            for br in bs:
                bs_br_matrix[bsidx, br_dict[br]] = True
        local_bs = np.full(len(self.data["branches"]), False)
        
        tmp_minset = []
        while local_bs.sum() < len(self.data["branches"]):
            tmp_sum = bs_br_matrix.sum(axis=1)
            max_value = tmp_sum.max()
            tmp_bsidxes = np.where(tmp_sum == max_value)[0]
            new_bsidx = tmp_bsidxes[coverage_list[tmp_bsidxes].argmax()]
            tmp_minset.append(new_bsidx)
            local_bs += bs_br_matrix[new_bsidx]
            bs_br_matrix[:, np.where(local_bs)[0]] = False
        return tmp_minset

    def cluster_naive(self):
        return list(self.data["bsidx_clusters"].keys())
    
    def extract_feature(self):
        cluster_set = None
        if self.main_option == "featmaker":
            cluster_set = self.cluster_setcover()
            self.data["features"] = set()
            for bsidx in cluster_set:
                for pcidx in self.data["bsidx_clusters"][bsidx]:
                    self.data["features"] |= set(self.data["unique pc"][pcidx])
            self.data["features"] = abstract_condition(self.data["features"])
        else:
            cluster_set = self.cluster_naive()
            self.data["features"] = set()
            for bsidx in cluster_set:
                 self.data["features"] |= get_pc_naive(self.data["bsidx_clusters"][bsidx])

    def extract_feature_fromhomi(self):
        feat_set = set()

        Symbolic_arg = "arg"
        Nonsymbolic_arg = "const_arr"
        Eq_expr = "Eq"
        Neq_expr = "false"

        cluster_set = self.cluster_setcover()
        self.data["features"] = set()

        for bsidx in cluster_set:
            for pcidx in self.data["bsidx_clusters"][bsidx]:
                self.data["features"] |= set(self.data["unique pc"][pcidx])

        for query in self.data["features"]:
            if ((Eq_expr in query) and (Symbolic_arg in query)
                and (Neq_expr not in query) and (Nonsymbolic_arg not in query)):

                feature = query.split('\n')[0]
                if (len(feat_set) < 200):
                    feat_set.add(feature)
                else:
                    break

        if self.mode == "medium":
            self.tempHomiFeat = feat_set.copy()
        else:
            self.data["features"] = feat_set
        # self.data["features"] = abstract_condition(self.data["features"])

    def extract_feature_homi(self):
        cluster_set = self.cluster_setcover()
        self.data["features"] = set()
        for bsidx in cluster_set:
            for pcidx in self.data["bsidx_clusters"][bsidx]:
                self.data["features"] |= set(self.data["unique pc"][pcidx])

        if self.mode == "medium":
            self.tempFMFeat = abstract_condition(self.data["features"])
        else:
            self.data["features"] = abstract_condition(self.data["features"])

    def feature_assignment(self):

        print("The Size of Features Set : ", len(self.tempHomiFeat), len(self.tempFMFeat))
        if len(self.tempHomiFeat) <= len(self.tempFMFeat):
            diff_set = self.tempFMFeat - self.tempHomiFeat

            if len(self.tempHomiFeat) <= len(diff_set):
                self.data["features"] = diff_set.copy()
            else:
                if random.random() < 0.5: 
                    self.data["features"] = self.tempHomiFeat.copy()
                else:
                    self.data["features"] = self.tempFMFeat.copy()

        else:
            diff_set = self.tempHomiFeat - self.tempFMFeat

            if len(self.tempFMFeat) <= len(diff_set):
                self.data["features"] = diff_set.copy()
            else:
                if random.random() < 0.5: 
                    self.data["features"] = self.tempFMFeat.copy()
                else:
                    self.data["features"] = self.tempHomiFeat.copy()
