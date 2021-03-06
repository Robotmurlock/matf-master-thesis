import os

import configparser
from utils import steps
from evaluation import eval
from datasets.vectornet_dataset import GraphScenarioDataset
from architectures.vectornet import TargetDrivenForecaster, LiteTNTLoss
import conventions


def run(config: configparser.GlobalConfig):
    model = TargetDrivenForecaster.load_from_checkpoint(
        checkpoint_path=os.path.join(config.global_path, config.evaluation.model_path, 'last.ckpt'),
        cluster_size=20,
        trajectory_length=30,
        polyline_features=14,
        n_targets=6
    )
    loss = LiteTNTLoss()

    datasets_path = os.path.join(config.global_path, config.evaluation.input_path)
    outputs_path = os.path.join(config.global_path, config.evaluation.output_path)
    for split_name in conventions.SPLIT_NAMES:
        ds_path = os.path.join(datasets_path, split_name)

        dataset = GraphScenarioDataset(ds_path)
        eval.evaluate(
            model=model,
            loss=loss,
            dataset=dataset,
            output_path=os.path.join(outputs_path, split_name),
            device='cuda',
            visualize=config.evaluation.visualize,
            scale=config.graph.data_process.normalization_parameter,
            title=split_name
        )


if __name__ == '__main__':
    run(configparser.config_from_yaml(steps.get_config_path()))
