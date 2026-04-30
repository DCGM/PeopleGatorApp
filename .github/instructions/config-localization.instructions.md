---
description: "Use when implementing functions, classes, or methods that consume configuration. Enforces localized, component-specific config patterns instead of passing entire TrainConfig hierarchies."
name: "Config Localization"
applyTo: "**/*.py"
---

# Config Localization

## Core Principle

Every function, class, and method should receive **only the specific config objects it actually needs**, never the entire `TrainConfig` hierarchy.

## Why This Matters

- **Decoupling**: Components don't depend on unrelated config sections
- **Clarity**: Function signatures explicitly declare config requirements
- **Testability**: Easier to test components with minimal, focused configs
- **Maintainability**: Changes to unrelated config sections don't break components
- **Reusability**: Components can be used independently with different config sources

## The Pattern

### Bad ❌
```python
def build_backbone(cfg: TrainConfig) -> tuple[nn.Module, int]:
    """Build backbone from full config."""
    backbone = timm.create_model(
        cfg.backbone.model_name,      # Uses backbone config
        pretrained=cfg.backbone.pretrained,
    )
    dummy = torch.randn(1, 3, cfg.data.image_size, cfg.data.image_size)  # Uses data config
    feature_dim = backbone(dummy).shape[1]
    return backbone, feature_dim
```

**Problems**:
- Function depends on two unrelated config sections
- Can't tell from signature what config is needed
- Hard to test with partial configs
- Breaks if `TrainConfig` structure changes

### Good ✅
```python
def build_backbone(
    backbone_cfg: BackboneConfig, image_size: int
) -> tuple[nn.Module, int]:
    """Build backbone from specific configs."""
    backbone = timm.create_model(
        backbone_cfg.model_name,
        pretrained=backbone_cfg.pretrained,
    )
    dummy = torch.randn(1, 3, image_size, image_size)
    feature_dim = backbone(dummy).shape[1]
    return backbone, feature_dim
```

**Benefits**:
- Signature clearly shows requirements
- Only depends on what it uses
- Easy to test independently
- Robust to config structure changes

## Rules

### 1. Extract Exact Requirements
Analyze what config fields a function actually uses, then pass only those.

```python
# Before: passing full config
def build_transform(cfg: TrainConfig) -> T.Compose:
    aug_cfg = cfg.task.augmentations
    image_size = cfg.data.image_size
    # ... uses aug_cfg and image_size only

# After: pass exact requirements
def build_transform(
    image_size: int, augmentations_cfg: AugmentationsConfig
) -> T.Compose:
    # ... uses augmentations_cfg and image_size directly
```

### 2. Use Specific Config Types
Always use the most specific config dataclass, never generic `dict` or `object`.

```python
# ✓ Good
def apply_freeze_strategy(backbone: nn.Module, backbone_cfg: BackboneConfig) -> None:

# ✗ Bad
def apply_freeze_strategy(backbone: nn.Module, cfg: dict) -> None:
def apply_freeze_strategy(backbone: nn.Module, cfg: Any) -> None:
```

### 3. Pass Primitives When Needed
Extract scalar values from configs if that's all that's needed.

```python
# ✓ Good: Pass the image_size value directly
def build_backbone(backbone_cfg: BackboneConfig, image_size: int) -> tuple[nn.Module, int]:

# ✗ Less ideal: Pass entire data config just for image_size
def build_backbone(backbone_cfg: BackboneConfig, data_cfg: DataConfig) -> tuple[nn.Module, int]:
    image_size = data_cfg.image_size
```

### 4. Exception: Orchestrators
Functions that coordinate multiple components can accept full configs since they need to pass different parts to different components.

```python
# ✓ OK: build_module orchestrates component creation
def build_module(cfg: TrainConfig) -> tuple[L.LightningModule, L.LightningDataModule]:
    datamodule = FinetuneDataModule(cfg.paths, cfg.data, cfg.task.augmentations, ...)
    model = FinetuneModule(cfg.backbone, cfg.task.loss, ...)
    return model, datamodule

# ✗ Bad: individual component should not take full config
class FinetuneModule(L.LightningModule):
    def __init__(self, cfg: TrainConfig, num_classes: int):  # Wrong!
```

## Refactoring Checklist

When refactoring a function to use localized configs:

- [ ] Identify all config fields the function actually uses
- [ ] Create function signature with exact config types needed
- [ ] Update all function calls to pass the right configs
- [ ] Remove `self.cfg` storage if it's now unused
- [ ] Update type hints to be explicit
- [ ] Test with minimal config objects
- [ ] Update docstrings if signature changed significantly

## Applied Examples

### augmentations.py
```python
# Before
def build_finetune_train_transform(cfg: TrainConfig) -> T.Compose:
    aug_cfg = cfg.task.augmentations
    image_size = cfg.data.image_size

# After
def build_finetune_train_transform(
    image_size: int, augmentations_cfg: AugmentationsConfig
) -> T.Compose:
```

### models/backbone.py
```python
# Before
def build_backbone(cfg: TrainConfig) -> tuple[nn.Module, int]:
    backbone = timm.create_model(cfg.backbone.model_name, ...)
    dummy = torch.randn(1, 3, cfg.data.image_size, cfg.data.image_size)

# After
def build_backbone(
    backbone_cfg: BackboneConfig, image_size: int
) -> tuple[nn.Module, int]:
    backbone = timm.create_model(backbone_cfg.model_name, ...)
    dummy = torch.randn(1, 3, image_size, image_size)
```

### models/finetune_module.py
```python
# Before
class FinetuneModule(L.LightningModule):
    def __init__(self, cfg: TrainConfig, num_classes: int):
        self.cfg = cfg
        self.backbone, feature_dim = build_backbone(cfg)
        self.criterion = build_loss(cfg.task.loss, cfg.backbone.embedding_dim, num_classes)

# After
class FinetuneModule(L.LightningModule):
    def __init__(
        self,
        backbone_cfg: BackboneConfig,
        loss_cfg: LossConfig,
        num_classes: int,
        image_size: int,
    ):
        self.save_hyperparameters()
        self.backbone, feature_dim = build_backbone(backbone_cfg, image_size)
        self.criterion = build_loss(loss_cfg, backbone_cfg.embedding_dim, num_classes)
```

### data_modules/datamodule.py
```python
# Before
class FinetuneDataModule(L.LightningDataModule):
    def __init__(self, cfg: TrainConfig):
        self.cfg = cfg
        train_transform = build_finetune_train_transform(self.cfg)

# After
class FinetuneDataModule(L.LightningDataModule):
    def __init__(
        self,
        paths_cfg: PathsConfig,
        data_cfg: DataConfig,
        augmentations_cfg: AugmentationsConfig,
        dataloader_cfg: DataloaderConfig,
        seed: int,
    ):
        self.paths_cfg = paths_cfg
        self.data_cfg = data_cfg
        self.augmentations_cfg = augmentations_cfg
        self.dataloader_cfg = dataloader_cfg
        self.seed = seed
        
        train_transform = build_finetune_train_transform(
            self.data_cfg.image_size, self.augmentations_cfg
        )
```

### train.py (Orchestrator - exception to the rule)
```python
# ✓ Correct: orchestrator receives full config
def build_module(cfg: TrainConfig) -> tuple[L.LightningModule, L.LightningDataModule]:
    # Passes specific parts to specific components
    datamodule = FinetuneDataModule(cfg.paths, cfg.data, cfg.task.augmentations, ...)
    model = FinetuneModule(cfg.backbone, cfg.task.loss, ...)
    return model, datamodule

# ✓ Correct: helper receives only what it needs
def build_callbacks(task_name: str, checkpoint_dir: str) -> list[Callback]:
    # Uses only task_name and checkpoint_dir, nothing else

# ✓ Correct: main training function can still use full config
def train(cfg: TrainConfig) -> None:
    # This is the entry point and orchestrates the whole training process
```

## Common Mistakes to Avoid

❌ Storing unused configs:
```python
def __init__(self, cfg: TrainConfig):
    self.cfg = cfg  # If you only use cfg.backbone, just take BackboneConfig
```

❌ Hiding config requirements:
```python
def build_something(cfg):  # What config is needed? Unclear!
```

❌ Over-extracting primitives:
```python
def build_something(model_name: str, pretrained: bool, drop_rate: float, ...):
    # Too many parameters; should accept BackboneConfig
```

❌ Ignoring type hints:
```python
def build_something(cfg: Any) -> None:  # Type is useless
    pass
```

## Testing

When writing tests for config-dependent code:

```python
def test_build_backbone():
    # Create minimal config object
    backbone_cfg = BackboneConfig(
        model_name="hf-hub:timm/edgenext_small.usi_in1k",
        pretrained=False,
    )
    image_size = 112
    
    # Call with exact requirements
    backbone, feature_dim = build_backbone(backbone_cfg, image_size)
    
    assert feature_dim == 1024  # Expected for the model
```

This is much easier than creating a full `TrainConfig` object with all nested configs.
