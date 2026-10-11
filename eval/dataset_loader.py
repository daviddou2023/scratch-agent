"""评估集与标注加载。"""

import json
from pathlib import Path

from eval.schema import EvalDataset, GoldLabels


DATASET_PATH = Path("data/eval/dataset.json")
LABELS_PATH = Path("data/eval/gold_labels.json")


def load_dataset(path: str | Path = DATASET_PATH) -> EvalDataset:
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"评估集不存在：{p}")
    data = json.loads(p.read_text(encoding="utf-8"))
    return EvalDataset.model_validate(data)


def load_gold_labels(path: str | Path = LABELS_PATH) -> GoldLabels:
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"标注文件不存在：{p}")
    data = json.loads(p.read_text(encoding="utf-8"))
    return GoldLabels.model_validate(data)