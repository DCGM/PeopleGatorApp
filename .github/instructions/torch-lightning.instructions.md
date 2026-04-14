---
description: "Use when implementing model training, fine-tuning, or experiment loops in Python. Prefer modern PyTorch 2.10+ patterns and Lightning for training workflows."
name: "Torch And Lightning Training"
applyTo: "**/*.py"
---
# Torch And Lightning Training

- For model training code, use modern PyTorch 2.10+ APIs and idioms.
- Use PyTorch Lightning as the training framework for trainers, loops, logging, checkpointing, and distributed setup.
- Do not add new raw PyTorch training loops in this repository.
- Write typed training code (modules, data modules, configs, and utility functions).
- Separate model definition, data pipeline, training orchestration, and evaluation into clear modules.
