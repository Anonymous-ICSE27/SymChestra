from . import filterSeeds
from sklearn.cluster import KMeans
from sklearn.cluster import MeanShift, estimate_bandwidth
import numpy as np
import random
import copy
import os

eta_num = 10
alpha = 1.1

def set_eta_num(num):
    global eta_num
    eta_num = num

def set_alpha(num):
    global alpha
    alpha = num

def returnBestFilteredSeedBadDifferentQueries(mode, datastructure, branchFrequency, usedBuffer,
                                              symtuner=None, log=None):
    scoreStructure = dict()

    copiedDS = copy.deepcopy(datastructure[mode])
    for eachUsed in usedBuffer:
        if eachUsed in copiedDS:
            copiedDS.pop(eachUsed)

    for tc, coverage in copiedDS.items():
        
        score = 0.0
        for eachB in coverage:
            score += 1 / branchFrequency[eachB]
        
        scoreStructure[tc] = score

    if len(scoreStructure) == 0:
        return None, None

    best_tcs = [name for name, _ in sorted(scoreStructure.items(), key=lambda x: -x[1])[:eta_num]]

    sorted_testcases = sorted(scoreStructure.items(), key=lambda x: x[1])
    num_to_return = min(eta_num, max(1, len(sorted_testcases) // 2))
    index = 0
    badQueriesDict = dict()

    seedQueryContents = list()
    for eachtc in best_tcs:
        seedQueryContent = filterSeeds.returnQueryContents(eachtc.replace("ktest", "kquery")).split("\n")
        del seedQueryContent[0]
        del seedQueryContent[-1]
        seedQueryContents.append(seedQueryContent)
    
    while True:
        if len(badQueriesDict) == num_to_return or len(badQueriesDict) == len(sorted_testcases):
            break
        
        curBadTc = sorted_testcases[index][0]
        curBadQuery = "/".join(["/".join(curBadTc.split("/")[:-1]), curBadTc.split("/")[-1].replace("ktest", "kquery")])

        if not os.path.exists(curBadQuery):
            index += 1
            continue
        
        curBadQueryContent = filterSeeds.returnQueryContents(curBadQuery).split("\n")
        del curBadQueryContent[0]
        del curBadQueryContent[-1]

        index_Seed = 0
        index_Bad = 0

        for seedQueryContent in seedQueryContents:
            while index_Seed < len(seedQueryContent) and index_Bad < len(curBadQueryContent):
                if seedQueryContent[index_Seed] == curBadQueryContent[index_Bad]:
                    index_Seed += 1
                    index_Bad += 1
                else:
                    break
            
            removedBadQueryContent = "\n".join(curBadQueryContent[index_Bad:])

            if removedBadQueryContent not in badQueriesDict:
                badQueriesDict[removedBadQueryContent] = curBadQuery
                break

        index += 1            
    
    badQueries = list(badQueriesDict.values())

    for each_tc in best_tcs:
        usedBuffer.append(each_tc)

        for branch in copiedDS[each_tc]:
            symtuner.branchPerScore[mode][branch] = symtuner.branchPerScore[mode].get(branch) * alpha
        
    for eachQuery in badQueries:
        usedBuffer.append(eachQuery.replace("kquery", "ktest"))

    return best_tcs, badQueries
