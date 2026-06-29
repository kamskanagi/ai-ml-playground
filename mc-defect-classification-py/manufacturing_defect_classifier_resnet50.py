"""
Manufacturing Defect Classifier — ResNet-50 Transfer Learning
=============================================================

Classifies product images into defect categories (e.g. good product vs.
various defect types) using a pretrained ResNet-50 backbone.

Pipeline
--------
1. Load a labelled image dataset organised as:
       my_defect_dataset/
           train/  <class_name>/  *.png
           val/    <class_name>/  *.png
           test/   <class_name>/  *.png
2. Fine-tune only the final classification head for NUM_EPOCHS epochs (fast,
   low risk of catastrophic forgetting).
3. Re-train all layers with class-weighted loss for NUM_EPOCHS_FINE_TUNE epochs
   to handle any class imbalance in the dataset.
4. Evaluate both models on the held-out test set (confusion matrix + per-class
   precision / recall / F1).
5. Run single-image inference to demonstrate deployment usage.

Background
----------
This script is the hands-on companion to the article:
"Machine Vision Defect Detection — A Complete Beginner's Guide"
https://www.labskaramind.com/post/machine-vision-defect-detection-a-complete-beginners-guide

The article covers the theory (CNNs, transfer learning, the capture → classify →
act pipeline); this code puts it into practice.

Usage
-----
    python manufacturing_defect_classifier_resnet50.py

The best checkpoint from each training phase is saved to disk so you can
re-load it later without re-training.
"""

import copy
import os
import time

import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F
import torch.optim as optim
from PIL import Image
from sklearn.metrics import confusion_matrix, precision_recall_fscore_support
from torch.utils.data import DataLoader
from torchvision import datasets, models, transforms


# ── Configuration ─────────────────────────────────────────────────────────────

DATA_DIR        = 'my_defect_dataset'   # root folder produced by data_organizer.py
BATCH_SIZE      = 32

# Phase 1 — train the classification head only (backbone frozen)
NUM_EPOCHS      = 5
LEARNING_RATE   = 0.001
MODEL_SAVE_PATH = 'best_defect_classifier_multi_category.pth'

# Phase 2 — full fine-tune with class-weighted loss (all layers unfrozen)
NUM_EPOCHS_FINE_TUNE   = 15
LEARNING_RATE_FINE_TUNE = 0.0001        # lower LR protects pretrained features
FINE_TUNE_SAVE_PATH    = 'best_fine_tuned_classifier.pth'

# Single-image inference demo — update this path to test a different image
SAMPLE_IMAGE_PATH = 'my_defect_dataset/test/defective_product/screw_test_manipulated_front_009.png'

# ImageNet statistics — required because the ResNet-50 backbone was pretrained
# on ImageNet; using the same normalisation keeps feature representations valid.
IMAGENET_MEAN = [0.485, 0.456, 0.406]
IMAGENET_STD  = [0.229, 0.224, 0.225]

# Training augmentation reduces overfitting on small manufacturing datasets.
train_transforms = transforms.Compose([
    transforms.RandomResizedCrop(224, scale=(0.8, 1.0)),
    transforms.RandomHorizontalFlip(),
    transforms.RandomVerticalFlip(),
    transforms.RandomRotation(15),
    transforms.ColorJitter(brightness=0.1, contrast=0.1, saturation=0.1, hue=0.05),
    transforms.ToTensor(),
    transforms.Normalize(IMAGENET_MEAN, IMAGENET_STD),
])

# Validation / test images are only resized and normalised — no random ops so
# results are deterministic and comparable across runs.
val_test_transforms = transforms.Compose([
    transforms.Resize(256),
    transforms.CenterCrop(224),
    transforms.ToTensor(),
    transforms.Normalize(IMAGENET_MEAN, IMAGENET_STD),
])


# ── Data loading ──────────────────────────────────────────────────────────────

def load_data(data_dir):
    """Load train / val / test splits from an ImageFolder directory layout.

    Returns
    -------
    image_datasets : dict[str, ImageFolder]
    dataloaders    : dict[str, DataLoader]
    dataset_sizes  : dict[str, int]
    class_names    : list[str]   – ordered list matching model output indices
    """
    image_datasets = {
        'train': datasets.ImageFolder(os.path.join(data_dir, 'train'), train_transforms),
        'val':   datasets.ImageFolder(os.path.join(data_dir, 'val'),   val_test_transforms),
        'test':  datasets.ImageFolder(os.path.join(data_dir, 'test'),  val_test_transforms),
    }

    # num_workers=0 avoids multiprocessing issues on macOS / Windows
    dataloaders = {
        split: DataLoader(
            image_datasets[split],
            batch_size=BATCH_SIZE,
            shuffle=(split == 'train'),
            num_workers=0,
        )
        for split in ['train', 'val', 'test']
    }

    dataset_sizes = {split: len(image_datasets[split]) for split in image_datasets}
    class_names   = image_datasets['train'].classes

    return image_datasets, dataloaders, dataset_sizes, class_names


# ── Model setup ───────────────────────────────────────────────────────────────

def build_model(num_classes, device):
    """Return a ResNet-50 adapted for *num_classes* output classes.

    Transfer-learning strategy
    --------------------------
    All convolutional layers are frozen so we only update the final Linear
    layer.  This is fast and prevents overwriting useful low-level features
    (edges, textures) already learnt from ImageNet.  The full network is
    unfrozen later during fine-tuning (see `unfreeze_all_layers`).
    """
    model = models.resnet50(weights=models.ResNet50_Weights.IMAGENET1K_V1)

    for param in model.parameters():
        param.requires_grad = False  # freeze backbone

    num_ftrs = model.fc.in_features
    model.fc = nn.Linear(num_ftrs, num_classes)  # replace head for our classes

    return model.to(device)


def unfreeze_all_layers(model):
    """Allow gradients to flow through every layer for full fine-tuning."""
    for param in model.parameters():
        param.requires_grad = True


# ── Training ──────────────────────────────────────────────────────────────────

def train_model(model, dataloaders, dataset_sizes, criterion, optimizer,
                device, num_epochs):
    """Train *model* for *num_epochs*, saving the best validation checkpoint.

    Parameters
    ----------
    model         : nn.Module
    dataloaders   : dict with 'train' and 'val' DataLoaders
    dataset_sizes : dict with sample counts for each split
    criterion     : loss function
    optimizer     : optimiser
    device        : torch.device
    num_epochs    : int

    Returns
    -------
    model : nn.Module – loaded with the best validation-accuracy weights
    """
    since          = time.time()
    # deepcopy stores a full duplicate of all weights in memory — acceptable here
    # but scales poorly for very large models (e.g. ViTs with hundreds of layers).
    best_model_wts = copy.deepcopy(model.state_dict())
    best_acc       = 0.0

    for epoch in range(num_epochs):
        print(f'Epoch {epoch + 1}/{num_epochs}')
        print('-' * 10)

        for phase in ['train', 'val']:
            model.train() if phase == 'train' else model.eval()

            running_loss     = 0.0
            running_corrects = 0

            for inputs, labels in dataloaders[phase]:
                inputs = inputs.to(device)
                labels = labels.to(device)

                optimizer.zero_grad()

                # Gradients are only needed during training
                with torch.set_grad_enabled(phase == 'train'):
                    outputs = model(inputs)
                    _, preds = torch.max(outputs, 1)
                    loss = criterion(outputs, labels)

                    if phase == 'train':
                        loss.backward()
                        optimizer.step()

                running_loss     += loss.item() * inputs.size(0)
                running_corrects += torch.sum(preds == labels.data)

            epoch_loss = running_loss / dataset_sizes[phase]
            epoch_acc  = running_corrects.float() / dataset_sizes[phase]
            print(f'{phase} Loss: {epoch_loss:.4f}  Acc: {epoch_acc:.4f}')

            # Keep a snapshot of the best model seen so far
            if phase == 'val' and epoch_acc > best_acc:
                best_acc       = epoch_acc
                best_model_wts = copy.deepcopy(model.state_dict())

        print()

    elapsed = time.time() - since
    print(f'Training complete in {elapsed // 60:.0f}m {elapsed % 60:.0f}s')
    print(f'Best val Acc: {best_acc:.4f}')

    model.load_state_dict(best_model_wts)
    return model


# ── Evaluation ────────────────────────────────────────────────────────────────

def evaluate_model(model, dataloaders, class_names, device):
    """Print confusion matrix and per-class precision / recall / F1 on test set.

    Parameters
    ----------
    model       : nn.Module – must already be on *device*
    dataloaders : dict containing a 'test' DataLoader
    class_names : list[str]
    device      : torch.device
    """
    model.eval()
    all_preds  = []
    all_labels = []

    print("\nRunning evaluation on test set...")
    with torch.no_grad():
        for inputs, labels in dataloaders['test']:
            inputs  = inputs.to(device)
            outputs = model(inputs)
            _, preds = torch.max(outputs, 1)
            all_preds.extend(preds.cpu().numpy())
            all_labels.extend(labels.numpy())

    cm = confusion_matrix(all_labels, all_preds)
    precision, recall, f1_score, _ = precision_recall_fscore_support(
        all_labels, all_preds,
        average=None,
        labels=np.arange(len(class_names)),
    )

    print("\n--- Test Set Results ---")
    print("Confusion Matrix:")
    print(cm)
    print("\nPer-class metrics:")
    for i, name in enumerate(class_names):
        print(f"  {name}")
        print(f"    Precision: {precision[i]:.4f}")
        print(f"    Recall:    {recall[i]:.4f}")
        print(f"    F1-score:  {f1_score[i]:.4f}")

    overall_acc = np.sum(np.array(all_preds) == np.array(all_labels)) / len(all_labels)
    print(f"\nOverall Test Accuracy: {overall_acc:.4f}")


# ── Single-image inference ────────────────────────────────────────────────────

def load_model_for_inference(checkpoint_path, num_classes, device):
    """Rebuild the ResNet-50 head and load saved weights for inference."""
    model = models.resnet50(weights=None)
    model.fc = nn.Linear(model.fc.in_features, num_classes)
    model.load_state_dict(torch.load(checkpoint_path, map_location=device))
    model = model.to(device)
    model.eval()
    return model


def predict_image(image_path, model, transform, class_names, device):
    """Classify a single image and return the predicted class and confidence.

    Parameters
    ----------
    image_path  : str – path to a PNG / JPEG file
    model       : nn.Module in eval mode
    transform   : torchvision transform pipeline
    class_names : list[str]
    device      : torch.device

    Returns
    -------
    predicted_class : str
    confidence      : float  (0–1)
    """
    image        = Image.open(image_path).convert('RGB')
    image_tensor = transform(image).unsqueeze(0).to(device)  # add batch dimension

    with torch.no_grad():
        output        = model(image_tensor)
        probabilities = F.softmax(output, dim=1)

    confidence, predicted_idx = torch.max(probabilities, 1)
    predicted_class = class_names[predicted_idx.item()]
    return predicted_class, confidence.item()


# ── Main pipeline ─────────────────────────────────────────────────────────────

def main():
    # --- Device selection ---
    if torch.cuda.is_available():
        device = torch.device('cuda:0')
    elif torch.backends.mps.is_available():
        device = torch.device('mps')   # Apple Silicon GPU
    else:
        device = torch.device('cpu')
    print(f"Using device: {device}")

    # --- Data ---
    print("\nLoading datasets...")
    image_datasets, dataloaders, dataset_sizes, class_names = load_data(DATA_DIR)
    num_classes = len(class_names)
    print(f"Dataset sizes:          {dataset_sizes}")
    print(f"Classes ({num_classes}): {class_names}")

    # --- Phase 1: train the classification head only ---
    print("\n=== Phase 1: Head-only training ===")
    model     = build_model(num_classes, device)
    criterion = nn.CrossEntropyLoss()
    optimizer = optim.Adam(model.fc.parameters(), lr=LEARNING_RATE)

    model = train_model(
        model, dataloaders, dataset_sizes,
        criterion, optimizer, device,
        num_epochs=NUM_EPOCHS,
    )
    torch.save(model.state_dict(), MODEL_SAVE_PATH)
    print(f"Checkpoint saved → {MODEL_SAVE_PATH}")

    evaluate_model(model, dataloaders, class_names, device)

    # --- Phase 2: full fine-tuning with class-weighted loss ---
    # Class-weighted loss up-weights minority classes so the model doesn't
    # simply learn to predict the majority class to minimise loss.
    print("\n=== Phase 2: Full fine-tuning (class-weighted) ===")

    train_counts = [0] * num_classes
    for _, label in image_datasets['train'].samples:
        train_counts[label] += 1

    total_samples = sum(train_counts)
    # Simplified weighting: total / count. The standard formula divides by
    # (num_classes * count) to keep loss magnitude near the unweighted baseline,
    # but this version works and is easier to follow for a teaching example.
    class_weights = (total_samples / torch.tensor(train_counts, dtype=torch.float)).to(device)
    print(f"Class counts:  {train_counts}")
    print(f"Class weights: {class_weights.tolist()}")

    criterion_weighted  = nn.CrossEntropyLoss(weight=class_weights)
    unfreeze_all_layers(model)
    optimizer_fine_tune = optim.Adam(model.parameters(), lr=LEARNING_RATE_FINE_TUNE)

    model = train_model(
        model, dataloaders, dataset_sizes,
        criterion_weighted, optimizer_fine_tune, device,
        num_epochs=NUM_EPOCHS_FINE_TUNE,
    )
    torch.save(model.state_dict(), FINE_TUNE_SAVE_PATH)
    print(f"Fine-tuned checkpoint saved → {FINE_TUNE_SAVE_PATH}")

    evaluate_model(model, dataloaders, class_names, device)

    # --- Single-image demo ---
    print("\n=== Single-image inference demo ===")
    if not os.path.exists(SAMPLE_IMAGE_PATH):
        print(f"Sample image not found, skipping demo: {SAMPLE_IMAGE_PATH}")
        return

    inference_model = load_model_for_inference(FINE_TUNE_SAVE_PATH, num_classes, device)

    predicted_class, confidence = predict_image(
        SAMPLE_IMAGE_PATH, inference_model, val_test_transforms, class_names, device,
    )
    print(f"Image:      {SAMPLE_IMAGE_PATH}")
    print(f"Prediction: {predicted_class}")
    print(f"Confidence: {confidence:.4f}")


if __name__ == '__main__':
    main()
