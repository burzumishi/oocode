#!/usr/bin/env python3
"""Runner principal de tests de OOCode — no consume tokens LLM.

Uso:
    python tests/run_tests.py              # todos los tests
    python tests/run_tests.py -v           # verbose
    python tests/run_tests.py -k git       # solo tests que contengan 'git'
    python tests/run_tests.py test_01      # solo módulo test_01
    python tests/run_tests.py --fast       # omite tests lentos (docker, LSP)
"""
import sys
import subprocess
from pathlib import Path

ROOT = Path(__file__).parent.parent
TESTS_DIR = Path(__file__).parent


def main():
    args = sys.argv[1:]
    pytest_args = [
        sys.executable, "-m", "pytest",
        str(TESTS_DIR),
        "--tb=short",
        "-q",
    ]
    pytest_args.extend(args)

    print(f"\n{'='*64}")
    print("  OOCode Test Suite — sin tokens LLM")
    print(f"{'='*64}\n")

    result = subprocess.run(pytest_args, cwd=str(ROOT))
    sys.exit(result.returncode)


if __name__ == "__main__":
    main()
