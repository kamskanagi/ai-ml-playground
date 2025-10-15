# GPT-OSS Fine-Tuning with Unsloth

This project demonstrates how to fine-tune OpenAI's GPT-OSS 20B model using Unsloth for efficient training on a free Google Colab Tesla T4 instance.

## Overview

This notebook provides a complete walkthrough of fine-tuning the GPT-OSS model with parameter-efficient LoRA adapters. The GPT-OSS models feature adjustable reasoning effort levels, allowing control over the trade-off between performance and response speed.

## Features

- **Efficient Fine-Tuning**: Uses Unsloth for 2x faster training with reduced memory usage
- **LoRA Adapters**: Parameter-efficient training (only 0.02% of parameters trained)
- **Adjustable Reasoning Effort**: Support for low, medium, and high reasoning levels
- **Multilingual Training**: Fine-tunes on the `HuggingFaceH4/Multilingual-Thinking` dataset
- **Memory Optimized**: Runs on free T4 GPU with 4-bit quantization

## Requirements

The notebook automatically installs all required dependencies:

- PyTorch (>=2.8.0)
- Transformers (4.56.2)
- Unsloth and Unsloth Zoo
- TRL (0.22.2)
- bitsandbytes

## Usage

### Running on Google Colab

1. Open the notebook in Google Colab
2. Select Runtime > Change runtime type > T4 GPU
3. Click Runtime > Run all

### Reasoning Effort Levels

The GPT-OSS models support three reasoning effort levels:

- **Low**: Fast responses for simple tasks
- **Medium**: Balanced performance and speed
- **High**: Maximum reasoning for complex tasks (higher latency)

### Training Configuration

- **Batch Size**: 1 per device with 4 gradient accumulation steps
- **Training Steps**: 30 (can be extended with `num_train_epochs=1`)
- **Learning Rate**: 2e-4 or 2e-4
- **LoRA Rank**: 8
- **Memory Usage**: ~13GB peak (1.1% for training)
- **Training Time**: ~10.76 minutes for 30 steps

## Dataset

The notebook uses the [HuggingFaceH4/Multilingual-Thinking](https://huggingface.co/datasets/HuggingFaceH4/Multilingual-Thinking) dataset, which contains reasoning chain-of-thought examples translated into multiple languages. This is the same dataset referenced in OpenAI's cookbook for fine-tuning. You can use any dataset of your choice to fine-tune the model.

## Model Saving

The notebook demonstrates multiple saving options:

1. **LoRA Adapters**: Save fine-tuned adapters locally or to Hugging Face Hub
2. **Float16 Format**: Merge and save in 16-bit for vLLM deployment
3. **MXFP4 Format**: Save in 4-bit format for efficient inference

```python
# Save locally
model.save_pretrained("finetuned_model")

# Push to Hugging Face Hub
model.push_to_hub("username/model_name", token="hf_...")
```

## Key Components

### Unsloth Features Used

- Fast model loading with automatic quantization
- LoRA adapter integration
- Response-only training (masks instruction tokens)
- Gradient checkpointing for memory efficiency
- Smart gradient offloading

### GPT-OSS Format

Uses OpenAI's [Harmony format](https://github.com/openai/harmony) which supports:

- Structured conversations
- Reasoning output channels (analysis, commentary, final)
- Tool calling capabilities

## References

- [Unsloth GitHub](https://github.com/unslothai/unsloth)
- [OpenAI GPT-OSS Cookbook](https://cookbook.openai.com/articles/gpt-oss/fine-tune-transfomers)
- [Harmony Format](https://github.com/openai/harmony)
- [Multilingual-Thinking Dataset](https://huggingface.co/datasets/HuggingFaceH4/Multilingual-Thinking)
