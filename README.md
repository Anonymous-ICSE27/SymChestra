# SymChestra
SymChestra is the first orchestration framework to integrate symbolic execution techniques that constructs the set of entry states for the next technique and finds the best-performing parameterized components, thereby maximizing the performance of symbolic execution.

# Installation
For ease of use, we would like to introduce Docker image for fast installation. You can just install SymChestra by following instructions.
```bash
$ docker build -t symchestra/icse27 .
$ docker run -it symchestra/icse27
```
In this dockerfile, we provide the scenario evaluated in our paper (SymTuner + FeatMaker + HOMI + KLEE-RAM) and 16 benchmark programs installation.

# How to execute SymChestra
To run SymChestra, execute the following command in the `/root/symchestra/` directory.
```bash
$ # SymChestra Mode
$ python3 bin_symchestra\(SFHR\).py sqlite symchestra_sqlite
$
$ # Sequence baseline
$ python3 bin_sequence\(SFHR\).py sqlite sequence_sqlite
$
$ # Union baseline
$ python3 bin_union\(SFHR\).py sqlite union_sqlite
```
Each argument of the command represents:
* sqlite : the program to be tested under our configuration ('sqlite' can be replaced by any programs installed in `/root/symchestra/benchmarks`.)
* symchestra_sqlite : the name of output directory (also can be replaced)

Furthermore, the following arguments can be specified as you like:
* --total_budget : the total time budget for your experiment (default setting in our evaluation is 24-hours, 86,400s)

If you want to evaluate the standalone techniques without any orchestration, you can execute the following commands.
```bash
$ python3 bin_standalone_symtuner.py sqlite standalone_symtuner_sqlite
$ python3 bin_standalone_featmaker.py sqlite standalone_featmaker_sqlite
$ python3 bin_standalone_homi.py sqlite standalone_homi_sqlite
$ python3 bin_standalone_kleeram.py sqlite standalone_kleeram_sqlite
```
In our dockerfile, we declare the techniques used in the paper scenario: SymTuner, FeatMaker, HOMI, and KLEE-RAM.

# Check the effectiveness of SymChestra in terms of code coverage and bug-finding ability
After the time budget is exhausted, the program displays the number of branches the technique achieved as follows:
```bash
$ Standalone {technique name} achieved X,XXX coverage.
$ Union-based integration of SymTuner+FeatMaker+HOMI+RAM achieved X,XXX coverage.
$ Sequence-based integration of SymTuner+FeatMaker+HOMI+RAM achieved X,XXX coverage.
$ SymChestra-based integration of SymTuner+FeatMaker+HOMI+RAM achieved X,XXX coverage.
```

Moreover, you can check the test cases triggering bugs as following directory:
```bash
/root/symchestra/symchestra_experiments/symchestra_sqlite/sqlite/found_bugs.txt
```
