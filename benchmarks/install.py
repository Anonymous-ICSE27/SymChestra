import subprocess
import argparse
import sys

BENCHMARKS = [
    "xorriso-1.5.2", "gawk-5.1.0", "gcal-4.1", "grep-3.6", "diffutils-3.7", "sed-4.8", "du-8.32", "patch-2.7.6", "ptx-8.32", "csplit-8.32", "m4-1.4.18", "ls-8.32", "enscript-1.6.6", "trueprint-5.4", "combine-0.4.0"    
]

COREUTILS = [
    "du-8.32", "ptx-8.32", "csplit-8.32", "ls-8.32"
]

def run_command(command):
    print(f"[MESSAGE] Executing : {command}")
    subprocess.run(command, shell=True, check=True)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Install and build benchmarks")
    parser.add_argument("--benchmark", type=str, help="Benchmark name to install", default=None)
    args = parser.parse_args()
    benchmark = args.benchmark

    if not benchmark:
        run_command("python3 install_benchmarks.py")
        run_command("bash install_sqlite.sh")
    else:
        if benchmark == "sqlite-3.33.0":
            run_command("bash install_sqlite.sh")
        elif benchmark in BENCHMARKS:
            print(f"[MESSAGE] Installing the program {benchmark}.")
            print(f"[MESSAGE] If you install the program of coreutils, you don't have to reinstall other progams of coreutils")
            print(f"[MESSAGE] Coreutils Programs : {COREUTILS}")
            if benchmark in COREUTILS:
                run_command(f"python3 install_benchmarks.py --benchmark=coreutils-8.32")        
            else:
                run_command(f"python3 install_benchmarks.py --benchmark={benchmark}")
        else:
            print(f"[ERROR] Not Found benchmark: {benchmark}")
            print(f"[ERROR] You need to check the available programs : {BENCHMARKS}")
            sys.exit(1)
