import subprocess
import sys

if __name__ == "__main__":
    ret = subprocess.run([sys.executable, "code/evaluation/test_aggressive_all_datasets.py"])
    sys.exit(ret.returncode)
