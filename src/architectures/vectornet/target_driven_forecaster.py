from typing import Dict, Optional
import torch
from pytorch_lightning import LightningModule

from architectures.vectornet.target_generator import TargetGenerator
from architectures.vectornet.trajectory_forecaster import TrajectoryForecaster
from architectures.vectornet.loss import LiteTNTLoss
from configparser import GraphTrainConfigParameters


class TargetDrivenForecaster(LightningModule):
    def __init__(
        self,
        cluster_size: int,
        trajectory_length: int,
        polyline_features: int,
        n_targets: int,

        train_config: Optional[GraphTrainConfigParameters] = None
    ):
        super(TargetDrivenForecaster, self).__init__()

        # model and loss
        self._n_targets = n_targets
        self._target_generator = TargetGenerator(cluster_size=cluster_size, polyline_features=polyline_features)
        self._trajectory_forecaster = TrajectoryForecaster(n_features=256, trajectory_length=trajectory_length)
        self._loss = LiteTNTLoss()

        # training
        self._train_config = train_config

        # logging
        self._log_history = {
            'training_loss': [],
            'training_tg_confidence_loss': [],
            'training_tg_huber_loss': [],
            'training_tf_huber_loss': [],
            'val_loss': [],
            'end_to_end_val_loss': []
        }

    def forward(self, polylines: torch.Tensor, anchors: torch.Tensor) -> Dict[str, torch.Tensor]:
        features, offsets, confidences = self._target_generator(polylines, anchors)
        targets = anchors + offsets

        n_batches = features.shape[0]
        batch_filtered_anchors, batch_filtered_offsets, batch_filtered_targets, batch_filtered_confidences = [], [], [], []
        for batch_index in range(n_batches):
            # for each instance in batch: choose top N targets
            instance_filter_indexes = torch.argsort(confidences[batch_index], descending=True)[:self._n_targets]
            instance_filtered_anchors = anchors[batch_index, instance_filter_indexes]
            instance_filtered_offsets = offsets[batch_index, instance_filter_indexes]
            instance_filtered_targets = targets[batch_index, instance_filter_indexes]
            instance_filtered_confidences = confidences[batch_index, instance_filter_indexes]

            batch_filtered_anchors.append(instance_filtered_anchors)
            batch_filtered_offsets.append(instance_filtered_offsets)
            batch_filtered_targets.append(instance_filtered_targets)
            batch_filtered_confidences.append(instance_filtered_confidences)

        # form batch from filtered targets
        filtered_anchors = torch.stack(batch_filtered_anchors)
        filtered_offsets = torch.stack(batch_filtered_offsets)
        filtered_targets = torch.stack(batch_filtered_targets)
        filtered_confidences = torch.stack(batch_filtered_confidences)

        trajectories = self._trajectory_forecaster(features, filtered_targets)
        return {
            'all_anchors': anchors,
            'all_offsets': offsets,
            'all_confidences': confidences,
            'anchors': filtered_anchors,
            'offsets': filtered_offsets,
            'targets': filtered_targets,
            'confidences': filtered_confidences,
            'forecasts': trajectories
        }

    def training_step(self, batch, *args, **kwargs) -> dict:
        polylines, anchors, ground_truth, gt_traj = batch

        # Generate targets from anchors
        features, offsets, confidences = self._target_generator(polylines, anchors)

        # Forecast trajectories for generated targets
        ground_truth_expanded = ground_truth.unsqueeze(1).repeat(1, self._n_targets, 1)
        forecasted_trajectories = self._trajectory_forecaster(features, ground_truth_expanded)

        loss, tg_ce_loss, tg_huber_loss, tf_huber_loss = \
            self._loss(anchors, offsets, confidences, ground_truth, forecasted_trajectories, gt_traj)

        self._log_history['training_loss'].append(loss)
        self._log_history['training_tg_confidence_loss'].append(tg_ce_loss)
        self._log_history['training_tg_huber_loss'].append(tg_huber_loss)
        self._log_history['training_tf_huber_loss'].append(tf_huber_loss)

        return loss

    def validation_step(self, batch, *args, **kwargs) -> dict:
        polylines, anchors, ground_truth, gt_traj = batch
        outputs = self(polylines, anchors)

        e2e_val_loss, _, _, _ = self._loss(
            anchors=outputs['all_anchors'],
            offsets=outputs['all_offsets'],
            confidences=outputs['all_confidences'],
            ground_truth=ground_truth,
            forecasts=outputs['forecasts'],
            gt_traj=gt_traj
        )

        self._log_history['end_to_end_val_loss'].append(e2e_val_loss)

        # FIXME: validation is logged into training loss :'(
        loss = self.training_step(batch, *args, **kwargs)
        self._log_history['val_loss'].append(loss)

        return loss

    def on_validation_epoch_end(self, *args, **kwargs) -> None:
        for log_name, sample in self._log_history.items():

            self.log(log_name, sum(sample) / len(sample), prog_bar=True)
            self._log_history[log_name] = []

    def configure_optimizers(self):
        assert self._train_config is not None, 'Error: Training config not set'
        tg_opt = torch.optim.Adam(self._target_generator.parameters(), lr=self._train_config.tg_lr)
        tf_opt = torch.optim.Adam(self._trajectory_forecaster.parameters(), lr=self._train_config.tf_lr)

        tg_sched = {
            'scheduler': torch.optim.lr_scheduler.StepLR(
                optimizer=tg_opt,
                step_size=self._train_config.tg_sched_step,
                gamma=self._train_config.tg_sched_gamma
            ),
            'interval': 'epoch',
            'frequency': 1
        }

        return [tg_opt, tf_opt], [tg_sched]


def test():
    polylines = torch.randn(4, 200, 20, 14)
    anchors = torch.randn(4, 75, 2)
    tdf = TargetDrivenForecaster(cluster_size=20, polyline_features=14, trajectory_length=20, n_targets=10)
    outputs = tdf(polylines, anchors)
    print(outputs['forecasts'].shape, outputs['confidences'].shape, outputs['targets'].shape)


if __name__ == '__main__':
    test()
