import re
from typing import TypedDict

# You can add multimodal datasets here and register a short nickname to ${data_dict}.
# The data format should follow the general multimodal VLM format, for example:
# https://github.com/QwenLM/Qwen2.5-VL/blob/main/qwen-vl-finetune/README.md

class DatasetConfig(TypedDict):
    annotation_path: str
    data_path: str


class SampledDatasetConfig(DatasetConfig):
    sampling_rate: float


json_root = "./playground/Datasets/LLaVA-OneVision-COCO/llava_jsons"
image_root = "./playground/Datasets/LLaVA-OneVision-COCO/images"

vlnce_root = "./playground/Datasets/VLN-CE"

SHAREGPT4V_COCO: DatasetConfig = {
    "annotation_path": f"{json_root}/sharegpt4v_coco.json",
    "data_path": f"{image_root}/",
}

R2R: DatasetConfig = {
    "annotation_path": f"{vlnce_root}/R2R/annotations_qwenvl.json",
    "data_path": f"{vlnce_root}/R2R/train/",
}

RXR: DatasetConfig = {
    "annotation_path": f"{vlnce_root}/RxR/annotations_qwenvl.json",
    "data_path": f"{vlnce_root}/RxR/train/",
}

data_dict: dict[str, DatasetConfig] = {
    "sharegpt4v_coco": SHAREGPT4V_COCO,
    "r2r": R2R,
    "rxr": RXR,
}

def parse_sampling_rate(dataset_name: str) -> float:
    match = re.search(r"%(\d+)$", dataset_name)
    if match:
        return int(match.group(1)) / 100.0
    return 1.0

def data_list(dataset_names: list[str]) -> list[SampledDatasetConfig]:
    if dataset_names == ["all"]:
        dataset_names = list(data_dict.keys())
    config_list: list[SampledDatasetConfig] = []
    for dataset_name in dataset_names:
        sampling_rate = parse_sampling_rate(dataset_name)
        dataset_name = re.sub(r"%(\d+)$", "", dataset_name)
        if dataset_name in data_dict.keys():
            config_list.append({**data_dict[dataset_name], "sampling_rate": sampling_rate})
        else:
            raise ValueError(f"do not find {dataset_name}")
    return config_list

if __name__ == "__main__":
    print(data_list)
    
