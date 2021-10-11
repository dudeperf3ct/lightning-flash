# Copyright The PyTorch Lightning team.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
from functools import partial
from typing import Callable, Dict, Optional

import pytest
import torch
from pytorch_lightning.trainer.states import RunningStage
from pytorch_lightning.utilities.exceptions import MisconfigurationException

from flash.core.data.preprocess_transform import PreTransform, PreTransformPlacement
from flash.core.registry import FlashRegistry


def test_preprocess_transform():

    transform = PreTransform(running_stage=RunningStage.TRAINING)

    assert str(transform) == "PreTransform(running_stage=train, transform=None)"

    def fn(x):
        return x + 1

    transform = PreTransform.from_transform(running_stage=RunningStage.TRAINING, transform=fn)
    assert transform.transform == {PreTransformPlacement.PER_SAMPLE_TRANSFORM: fn}

    class MyPreTransform(PreTransform):
        def configure_transforms(self) -> Optional[Dict[str, Callable]]:
            return None

    transform = MyPreTransform(running_stage=RunningStage.TRAINING)
    assert not transform._current_fn
    assert str(transform) == "MyPreTransform(running_stage=train, transform=None)"

    class MyPreTransform(PreTransform):
        def fn(self, x):
            return x + 1

        def configure_transforms(self) -> Optional[Dict[str, Callable]]:
            return {PreTransformPlacement.PER_SAMPLE_TRANSFORM: self.fn if self.training else fn}

    transform = MyPreTransform(running_stage=RunningStage.TRAINING)
    assert transform.transform == {PreTransformPlacement.PER_SAMPLE_TRANSFORM: transform.fn}

    transform._current_fn = "per_sample_transform"
    assert transform.current_transform == transform.fn
    assert transform.per_sample_transform(1) == 2
    assert transform.per_sample_transform([1, 2]) == [2, 3]

    transform._current_fn = "per_sample_transform_on_device"
    assert transform.current_transform == transform._identity
    assert transform.per_sample_transform_on_device(1) == 1
    assert transform.per_sample_transform_on_device([1, 2]) == [1, 2]

    transform._current_fn = "collate"
    assert transform.current_transform == transform._identity
    assert torch.equal(transform.collate([0, 1]), torch.tensor([0, 1]))

    transform._current_fn = "per_batch_transform"
    assert transform.current_transform == transform._identity
    assert transform.per_batch_transform(2) == 2

    transform = MyPreTransform(running_stage=RunningStage.TESTING)
    assert transform.transform == {PreTransformPlacement.PER_SAMPLE_TRANSFORM: fn}

    assert transform.transforms == {"transform": {PreTransformPlacement.PER_SAMPLE_TRANSFORM: fn}}

    class FailureMyPreTransform(PreTransform):
        def configure_transforms(self) -> Optional[Dict[str, Callable]]:
            return {"wrong_key": fn}

    with pytest.raises(MisconfigurationException, match="train_transform contains {'wrong_key'}"):
        transform = FailureMyPreTransform(running_stage=RunningStage.TRAINING)

    with pytest.raises(MisconfigurationException, match="test_transform contains {'wrong_key'}"):
        transform = FailureMyPreTransform(running_stage=RunningStage.TESTING)

    transform_registry = FlashRegistry("transforms")
    transform_registry(fn=MyPreTransform, name="something")

    transform = PreTransform.from_transform(
        running_stage=RunningStage.TRAINING, transform="something", transform_registry=transform_registry
    )

    transform = transform.from_transform(
        running_stage=RunningStage.TRAINING, transform=transform, transform_registry=transform_registry
    )

    assert isinstance(transform, MyPreTransform)
    assert transform.transform == {PreTransformPlacement.PER_SAMPLE_TRANSFORM: transform.fn}

    collate_fn = transform.dataloader_collate_fn
    assert collate_fn.collate_fn.func == transform.collate
    assert collate_fn.per_sample_transform.func == transform.per_sample_transform
    assert collate_fn.per_batch_transform.func == transform.per_batch_transform

    on_after_batch_transfer_fn = transform.on_after_batch_transfer_fn
    assert on_after_batch_transfer_fn.collate_fn.func == transform._identity
    assert on_after_batch_transfer_fn.per_sample_transform.func == transform.per_sample_transform_on_device
    assert on_after_batch_transfer_fn.per_batch_transform.func == transform.per_batch_transform_on_device

    assert transform._collate_in_worker_from_transform

    class MyPreTransform(PreTransform):
        def configure_transforms(self) -> Optional[Dict[str, Callable]]:
            return {
                PreTransformPlacement.PER_BATCH_TRANSFORM: fn,
                PreTransformPlacement.PER_SAMPLE_TRANSFORM_ON_DEVICE: fn,
            }

    with pytest.raises(MisconfigurationException, match="`per_batch_transform` and `per_sample_transform_on_device`"):
        transform = MyPreTransform(running_stage=RunningStage.TESTING)

    with pytest.raises(MisconfigurationException, match="The format for the transform isn't correct"):
        PreTransform.from_transform(1, running_stage=RunningStage.TRAINING)

    class MyPreTransform(PreTransform):
        def configure_transforms(self) -> Optional[Dict[str, Callable]]:
            return {
                PreTransformPlacement.COLLATE: fn,
                PreTransformPlacement.PER_SAMPLE_TRANSFORM_ON_DEVICE: fn,
                PreTransformPlacement.PER_BATCH_TRANSFORM_ON_DEVICE: fn,
            }

    transform = MyPreTransform(running_stage=RunningStage.TESTING)
    assert not transform._collate_in_worker_from_transform

    def compose(x, funcs):
        for f in funcs:
            x = f(x)
        return x

    transform = PreTransform.from_transform(
        transform=partial(compose, funcs=[fn, fn]), running_stage=RunningStage.TRAINING
    )
    assert transform[PreTransformPlacement.PER_SAMPLE_TRANSFORM](1) == 3
