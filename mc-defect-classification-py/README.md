# Defect Detection System for Manufacturing

> **Companion article:** [Machine Vision Defect Detection — A Complete Beginner's Guide](https://www.labskaramind.com/post/machine-vision-defect-detection-a-complete-beginners-guide)
> The article explains the *why* and the theory (CNNs, transfer learning, the capture → classify → act pipeline). This repo is the hands-on implementation.

## Project Overview
This project is a machine learning-based defect detection system for manufacturing. It uses a Convolutional Neural Network (CNN) and the PyTorch framework to automatically classify products as "Good" or "Defective" based on visual inspection. The system was developed as a proof-of-concept to demonstrate a robust pipeline for quality control in manufacturing.

## Problem Solved
The system automatically detects defects (e.g., scratches, dents, misprints) in products, which is a critical task for quality control in manufacturing. The model is trained to be robust in identifying defects even in a highly imbalanced dataset, a common challenge in real-world manufacturing scenarios.

## Key Features
- **Transfer Learning with ResNet-50:** The model leverages a pre-trained ResNet-50 model on the ImageNet dataset, allowing for faster training and superior feature extraction on a limited dataset.
- **Class Imbalance Handling:** The training process uses a weighted cross-entropy loss function to address the significant class imbalance between "Good" and "Defective" products. This ensures the model learns to prioritize the detection of rare defects.
- **Comprehensive Evaluation:** The model's final performance is thoroughly evaluated on a held-out test set using a confusion matrix, precision, recall, and F1-score to provide a clear and honest picture of its effectiveness.
- **Scalability:** The pipeline is designed to be scalable and can be retrained on new datasets to adapt to different product types or defect categories.
- **Apple Silicon (MPS) Support:** Training runs on Apple Silicon GPUs via PyTorch's MPS backend, in addition to CUDA and CPU.

## Model Performance

Training was conducted in two phases on a dataset of 355 training / 66 validation / 59 test images across two classes (`defective_product`, `good_product`).

### Phase 1 — Head-only Training (5 epochs, frozen backbone)

Only the final classification layer was trained; all ResNet-50 backbone weights were frozen.

- **Training time:** ~16 minutes (Apple M-series GPU)
- **Best val accuracy:** 78.8%
- **Test accuracy:** 79.7%

> At this stage the model predicts "good" for almost everything due to class imbalance (83 defective vs 272 good training images). The fine-tuning phase below corrects this.

### Phase 2 — Fine-tuning (15 epochs, weighted loss + unfrozen backbone)

All layers were unfrozen and trained with a weighted cross-entropy loss (defective class weight ≈ 4.3×) at a reduced learning rate (0.0001).

- **Training time:** ~10 minutes (Apple M-series GPU)
- **Best val accuracy:** 87.9%
- **Overall test accuracy:** **86.4%**

**Confusion Matrix (test set):**

```
                    Predicted: defective   Predicted: good
Actual: defective         10                    8
Actual: good               0                   41
```

**Per-class metrics:**

| Class              | Precision | Recall | F1-score |
|--------------------|-----------|--------|----------|
| defective_product  | 1.0000    | 0.5556 | 0.7143   |
| good_product       | 0.8367    | 1.0000 | 0.9111   |

**Single-image inference example:**
- Input: `my_defect_dataset/test/defective_product/screw_test_manipulated_front_009.png`
- Predicted: `defective_product` — Confidence: **86.2%**

> In a manufacturing context recall for defects matters most (missed defects reach customers). The fine-tuned model achieves zero false negatives for good products while catching ~56% of defects with 100% precision. Further improvement would require more defective training samples.

## Project Stack
- **Framework:** PyTorch (>= 2.0), torchvision
- **Libraries:** scikit-learn, numpy, Pillow
- **Data:** MVTec Anomaly Detection (AD) Dataset. The project combines multiple categories from this dataset to create a more generalized defect classifier.
- **Hardware:** Supports CUDA GPU, Apple Silicon (MPS), and CPU. Development and benchmarks were run on Apple Silicon.

---

## Getting Started: Local Setup

### 1. Prerequisites
- Python >= 3.9
- A GPU (CUDA or Apple Silicon MPS) is recommended for training; CPU works but is slower.

### 2. Virtual Environment and Dependencies

```bash
python -m venv venv

# macOS/Linux:
source venv/bin/activate
# Windows:
venv\Scripts\activate
```

### 3. Install required packages

```bash
pip install -r requirements.txt
```

### 4. Dataset Setup

The project uses a custom-organised dataset derived from the MVTec AD dataset, structured as:

```
my_defect_dataset/
    train/
        defective_product/   *.png
        good_product/        *.png
    val/
        defective_product/   *.png
        good_product/        *.png
    test/
        defective_product/   *.png
        good_product/        *.png
```

Download the [MVTec AD dataset](https://www.mvtec.com/company/research/datasets/mvtec-ad) and organise images into the structure above, or adapt it to your own product/defect categories.

### 5. Training and Evaluation

With your dataset in place, run the script:

```bash
python manufacturing_defect_classifier_resnet50.py
```

The script runs both training phases end-to-end and saves two checkpoints:
- `best_defect_classifier_multi_category.pth` — phase 1 (head-only) weights
- `best_fine_tuned_classifier.pth` — phase 2 (full fine-tune) weights

### 6. Running Tests

```bash
pip install -r requirements-dev.txt
python -m pytest tests/ -v
```

This runs:
- `tests/test_data_organizer.py` — verifies correct dataset splitting and no filename collisions.
- `tests/test_inference_smoke.py` — loads a sample image, runs it through ResNet-50, and checks for a valid output shape.

### Contributions
Contributions are welcome! Feel free to fork this repository, make improvements, and submit pull requests.
