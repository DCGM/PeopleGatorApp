---
description: "Use when implementing model training, fine-tuning, or experiment loops in Python. Prefer modern PyTorch 2.10+ patterns and Lightning for training workflows."
name: "Torch And Lightning Training"
applyTo: "*training/**/*.py,*train*.py,*experiments/**/*.py,*finetune*/**/*.py"
---
# Torch And Lightning Training

- For model training code, use modern PyTorch 2.10+ APIs and idioms.
- Always use structured Hydra configs for training experiments, with clear separation of model, data, and training parameters.
- Use PyTorch Lightning as the training framework for trainers, loops, logging, checkpointing, and distributed setup.
- Write typed training code (modules, data modules, configs, and utility functions).
- Use absolute package imports in training code; do not use relative imports.
- Keep the trainable backbone and task heads as top-level attributes on the LightningModule whenever practical, for example `self.backbone` and `self.head`.
- Prefer LightningModule-owned training logic over separate pure-PyTorch wrapper model classes; use helper functions to build submodules only when they keep the module readable.
- Keep model state that matters for training, freezing, EMA, and optimizer grouping inside the LightningModule so the training object remains the primary abstraction.
- Separate data pipeline, loss definitions, dataset definitions, training orchestration, and evaluation into clear modules.
- Use Lightning's `LightningModule` for model definition and training logic, and `LightningDataModule` for data loading and preprocessing.
- Any vision tasks should use `torchvision.io` for image loading and transformations. Output tensors should be in always from `torchvision.tv_tensors`, and the preprocessing pipeline should use exclusively `torchvision.transforms.v2` APIs.

## Do Not

- Do not add raw PyTorch training loops — extend existing `LightningModule` subclasses.
- Do not introduce standalone torch model wrapper classes for trainable backbones when the LightningModule can own them directly.
- Do not call `model.train()` / `model.eval()` manually inside Lightning modules — Lightning manages this.
- Do not hardcode device strings (`"cuda"`, `"cpu"`) — use Lightning's device abstractions.
- Do not log metrics with `print()` — use `self.log()` or Lightning's built-in logging hooks.
