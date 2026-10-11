"""评估报告入口：把 runs 目录下的结果渲染成 Markdown。

用法：
    python -m eval.run_report --tag baseline
"""

import argparse
import json
from pathlib import Path

from eval.report import render_run_summary, save_report
from eval.schema import RunResult


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tag", required=True, help="runs 文件名（不含 .json）")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    path = Path("data/eval/runs") / f"{args.tag}.json"
    if not path.exists():
        raise FileNotFoundError(f"结果文件不存在：{path}")

    data = json.loads(path.read_text(encoding="utf-8"))
    results = [RunResult.model_validate(r) for r in data]

    content = render_run_summary(results, title=f"评估报告：{args.tag}")
    out = save_report(content, args.tag)
    print(f"[saved] {out}")


if __name__ == "__main__":
    main()