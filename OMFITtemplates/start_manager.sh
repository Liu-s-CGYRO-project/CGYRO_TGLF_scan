#!/bin/sh
# Run from any working directory. A Conda/OMFIT Python may be selected explicitly.
set -eu
script_path=$(readlink -f -- "$0")
script_dir=$(dirname -- "$script_path")
python_bin=${OMFIT_TEMPLATE_PYTHON:-python3}
exec "$python_bin" "$script_dir/launch.py" "$@"
