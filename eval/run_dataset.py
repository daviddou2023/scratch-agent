"""Command-line entry point for running the evaluation dataset."""

import argparse
import asyncio
from pathlib import Path

from eval.dataset_loader import load_dataset, load_gold_labels
from eval.runner import run_dataset


DEFAULT_DATASET = Path("data/eval/runs/dataset.json")
DEFAULT_LABELS = Path("data/eval/runs/gold_labels.json")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the evaluation dataset and save structured results."
    )
    parser.add_argument(
        "--tag",
        default="baseline",
        help="Output file name without .json (default: baseline)",
    )
    parser.add_argument(
        "--dataset",
        type=Path,
        default=DEFAULT_DATASET,
        help=f"Dataset JSON path (default: {DEFAULT_DATASET})",
    )
    parser.add_argument(
        "--labels",
        type=Path,
        default=DEFAULT_LABELS,
        help=f"Gold labels JSON path (default: {DEFAULT_LABELS})",
    )
    parser.add_argument(
        "--videos",
        nargs="*",
        default=[],
        help="Optional video IDs to run; omit to run all videos.",
    )
    return parser.parse_args()


async def main() -> None:
    args = parse_args()
    dataset = load_dataset(args.dataset)
    labels = load_gold_labels(args.labels)

    videos = dataset.videos
    if args.videos:
        requested = set(args.videos)
        videos = [video for video in videos if video.video_id in requested]
        missing = requested - {video.video_id for video in videos}
        if missing:
            raise SystemExit(f"Unknown video IDs: {', '.join(sorted(missing))}")

    print(f"Running {len(videos)} videos with tag '{args.tag}'...")
    await run_dataset(
        videos=videos,
        labels=labels.labels,
        tag=args.tag,
    )


if __name__ == "__main__":
    asyncio.run(main())
