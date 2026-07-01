import os
import re

def returnQueryContents(query):  
    pattern = r'\(query \[.*?\] false\)'
    with open(query, "r") as file:
        content = file.read()
    match = re.search(pattern, content, re.DOTALL)
    extracted_text = match.group(0)
    
    return extracted_text

def checkAndUpdateQueries(tc, querystructure):
    query = tc.replace("ktest", "kquery")

    if not os.path.exists(query):
        return False 
    
    extracted_text = returnQueryContents(query)
    if extracted_text not in querystructure:
        querystructure.add(extracted_text)
        return True
    else:
        return False