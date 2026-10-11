"""实验入口：命令行运行。

用法：
    python -m eval.run_experiment --name topic_v2 --variable prompt_version \
        --baseline v1 --candidate v2_topic
"""

import argparse
import asyncio

from app.prompts.variants import get_variant
from eval.experiment import run_experiment
from eval.schema import ExperimentConfig


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--name", required=True, help="实验名")
    parser.add_argument("--variable", default="prompt_version", help="变量名")
    parser.add_argument("--baseline", default="v1", help="基线变体")
    parser.add_argument("--candidate", required=True, help="实验变体")
    parser.add_argument("--videos", nargs="*", default=[], help="限定视频 ID")
    return parser.parse_args()


async def main() -> None:
    args = parse_args()

    config = ExperimentConfig(
        name=args.name,
        variable=args.variable,
        baseline=args.baseline,
        candidate=args.candidate,
        video_ids=args.videos,
    )

    baseline_prompt = get_variant(args.baseline)
    candidate_prompt = get_variant(args.candidate)

    await run_experiment(config, baseline_prompt, candidate_prompt)


if __name__ == "__main__":
    asyncio.run(main())