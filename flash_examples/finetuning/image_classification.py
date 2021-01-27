# import our libraries
import pytorch_lightning as pl
import torch
from flash.vision import ImageClassificationData, ImageClassifier
from flash.vision.classification.dataset import hymenoptera_data_download

# 1. Download data
hymenoptera_data_download('data/')

# 2. Organize our data
datamodule = ImageClassificationData.from_folders(
    train_folder="data/hymenoptera_data/train/",
    valid_folder="data/hymenoptera_data/val/",
)

# 3. Build a model
model = ImageClassifier(num_classes=datamodule.num_classes)

# 4. Create trainer
trainer = pl.Trainer(max_epochs=1)

# 5. Train the model
trainer.fit(model, datamodule=datamodule)

# 6. Save model
torch.save(model, "image_classification_model.pt")