"""Build independent font packs; font bytes are never embedded in code."""
from build_font_resources import build
from pathlib import Path
import argparse
import json

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', required=True, type=Path)
    parser.add_argument('--license', required=True, type=Path)
    parser.add_argument('--plot-source', required=True, type=Path)
    parser.add_argument('--output-dir', required=True, type=Path)
    args = parser.parse_args()
    result = build(args.source, args.license, args.plot_source, args.output_dir)
    print(json.dumps(dict(paths=result['paths'], font_bytes_embedded=0)))
