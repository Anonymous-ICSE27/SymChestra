import os
import time
os_cmd = "find . -type f ! -name '__init__.py' ! -path './__pycache__/*' ! -path './homi_subscript/*' ! -name 'bin.py' ! -name 'bin_featmaker.py' ! -name 'bin_featmaker_base.py' ! -name 'bin_featmaker_parallel.py' ! -name 'bin_featmaker_control.py' ! -name 'bin_featmaker_half.py' ! -name 'bin_featmaker_random.py' ! -name 'bin_featmaker_seqBS.py' ! -name 'bin_featmaker_seqBSControl.py' ! -name 'symtuner.py' ! -name 'symbolic_executor.py' ! -name 'bin_homi.py' ! -name 'bin_featmaker_seqBSSym.py' ! -name 'combination_symfeat.py' ! -path './featmaker_subscript/*' ! -name 'homi_symtuner.py' ! -name 'klee.py' ! -name 'logger.py' ! -name 'resultFigure.py' ! -name 'monitor.py' ! -name 'bin_featmaker_seqTriple.py' ! -path './pgm_config/*' ! -delete"
while True:
    os.system(os_cmd)
    print("-DONE-")
    time.sleep(60)