#!/usr/bin/env bash
# TTU FactBook MC College Test & Verification Runner Script

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

if [ ! -d "venv" ]; then
    echo "Setting up virtual environment..."
    python3 -m venv venv
    ./venv/bin/pip install --upgrade pip
    ./venv/bin/pip install requests requests-ntlm beautifulsoup4 lxml tabulate rich
fi

# Check if running production faults tester or dev comparison tester
if [[ "$*" == *"--prod"* ]]; then
    NEW_ARGS=()
    for arg in "$@"; do
        if [ "$arg" != "--prod" ]; then
            NEW_ARGS+=("$arg")
        fi
    done
    ./venv/bin/python prod_functionality_tester.py "${NEW_ARGS[@]}"
else
    # Default: Dev vs Prod comparison tester
    ./venv/bin/python factbook_tester.py "$@"
fi
