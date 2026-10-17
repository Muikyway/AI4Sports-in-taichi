"""Download Qwen3 weights from ModelScope, never from Hugging Face."""
from __future__ import annotations

import argparse
import os
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", default="Qwen/Qwen3-8B-Base", help="ModelScope model id")
    parser.add_argument("--local-dir", required=True)
    args = parser.parse_args()
    os.environ["MODELSCOPE_CACHE"] = str(Path(args.local_dir).parent / ".modelscope_cache")
    try:
        from modelscope import snapshot_download
    except ImportError as exc:
        raise SystemExit("Install ModelScope first: pip install modelscope") from exc
    path = snapshot_download(args.model, local_dir=args.local_dir)
    print(f"downloaded from ModelScope: {path}")


if __name__ == "__main__":
    main()
