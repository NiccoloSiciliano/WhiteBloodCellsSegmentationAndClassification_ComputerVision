
import tensorflow as tf
import cv2
from tensorflow.keras.callbacks import EarlyStopping
from BinaryMask import BinaryMask
from utils import Utils
import os
import numpy as np
from var import clas, epochs, batch_size
from tensorflow.keras.optimizers import Adam

class Model:
	"""docstring for Model"""
	def __init__(self, src_path, n_classes):
		self.src_path = src_path
		self.n_classes = n_classes

	def load_model(self):
		self.model = tf.keras.models.load_model(self.src_path, custom_objects={'custom_metric':  Utils.multi_class_dice_coefficient}, safe_mode= False)

	def feed(self,inpt):
		inpt = tf.expand_dims(inpt, axis=0)
		return self.model.predict(inpt)[0]
	def compile_model(self):
		self.model.compile(
		optimizer='adam',
		loss='categorical_crossentropy',
		metrics=[lambda y_true, y_pred:  Utils.multi_class_dice_coefficient(y_true, y_pred)]
		)

	def train_model(self, dataset, val_dataset):
		early_stopping = EarlyStopping(
		    monitor='val_loss',  # The metric to monitor
		    patience=5,          # Number of epochs with no improvement after which training will be stopped
		    verbose=1,           # Verbosity mode
		    restore_best_weights=True  # Restore model weights from the epoch with the best value of the monitored quantity
		)
		self.model.fit(
		dataset,
		epochs=epochs,
		batch_size=batch_size,
		validation_data=val_dataset,
		callbacks=[early_stopping]  # List of callbacks to apply during training
		)
        
	def evaluate_model(self, dataset):
		# Iterate over the dataset
		tot_dice = 0
		tot_acc = 0
		tot_iou = 0
		count= 0
		dice_func = Utils.multi_class_dice_coefficient
		iou_func = Utils.compute_mean_iou
		accuracy_func = Utils.accuracy
		print(tf.data.experimental.cardinality(dataset).numpy())
		for batch_images,batch_masks in dataset:
			# Add batch dimension to single images if needed
			batch_masks = batch_masks.numpy()
			batch_images = batch_images.numpy()
			for i in range(batch_masks.shape[0]):
				inpt = tf.convert_to_tensor(batch_images[i])
				pred_masks = self.feed(inpt)
				dice_per_img = dice_func(batch_masks[i],Utils.one_hot_vec(pred_masks))
				iou_per_img = iou_func(batch_masks[i], Utils.one_hot_vec(pred_masks), 3)
				accuracy_per_img = accuracy_func(batch_masks[i],Utils.one_hot_vec(pred_masks))
				tot_dice += dice_per_img
				tot_iou += iou_per_img
				tot_acc += accuracy_per_img
				count+=1
		return tot_acc/count,tot_dice/count, tot_iou/count
    
	def build_CNN(self):

		self.model = Utils.get_wall_arch(self.n_classes)

		self.model.summary()

	def save(self, path):
		self.model.save(path)

class TwoModelArch(Model):
	"""docstring for Model"""
	def __init__(self, src_path1, src_path2,n_classes):
		self.model1 = Model(src_path1,2)
		self.model2 = Model(src_path2,2)

	def load_model(self):
		self.model1.load_model()
		self.model2.load_model()

	def feed(self,inpt):
		#Predict cell walls
		pred_wall = Utils.one_hot_vec(self.model1.feed(inpt))
		
		b_pred_wall = BinaryMask(pred_wall)
		
		pred_nuc = Utils.one_hot_vec(self.model2.feed(b_pred_wall.get_masked_image(inpt)))

		v = tf.concat(( tf.expand_dims(pred_wall[:,:,0], axis=-1), tf.expand_dims(pred_nuc[:,:,1], axis=-1), tf.expand_dims(pred_wall[:,:,1], axis=-1)), axis = -1)


		return v.numpy()



class ClassificationModel:
	def __init__(self, src_path, n_classes):
		self.src_path = src_path
		self.n_classes = n_classes

	def load_model(self):
		self.model = tf.keras.models.load_model(self.src_path, safe_mode= False)

	def feed(self,inpt):
		inpt = tf.expand_dims(inpt, axis=0)
		return self.model.predict(inpt)[0]

	def compile_model(self):
		self.model.compile(
		    loss='categorical_crossentropy',
		    optimizer=Adam(learning_rate=0.0001),
		    metrics=['accuracy']
		)

	def train_model(self, dataset, val_dataset):
		early_stopping = EarlyStopping(
		    monitor='val_loss',  # The metric to monitor
		    patience=10,          # Number of epochs with no improvement after which training will be stopped
		    verbose=1,           # Verbosity mode
		    restore_best_weights=True  # Restore model weights from the epoch with the best value of the monitored quantity
		)
		self.model.fit(
		dataset,
		epochs=epochs,
		batch_size=batch_size,
		validation_data=val_dataset,
		callbacks=[early_stopping]  # List of callbacks to apply during training
		)

	def build_CNN(self):

		self.model = Utils.get_arch_classification(self.n_classes)

		self.model.summary()

	def save(self, path):
		self.model.save(path)
	def get_model(self):
		return self.model

	def evaluate_model(self, dataset_path):
		test_dataset = Utils.create_classification_dataset(dataset_path)
		# Evaluate the model
		y_pred_probs = self.model.predict(test_dataset)

		# Convert predicted probabilities to class indices (i.e., predicted labels)
		y_pred = np.argmax(y_pred_probs, axis=1)

		# Get the true labels from the test dataset
		y_true = test_dataset.classes  
		return Utils.classification_metrics(y_true, y_pred)

class SegmentationModelClass(Model):
	def __init__(self, src_path, n_classes):
		self.src_path = src_path
		self.n_classes = n_classes

	def feed(self,inpt, clas):
		inpt = tf.expand_dims(inpt, axis=0)
		clas = tf.expand_dims(clas, axis=0)

		return self.model.predict([inpt, clas])[0]

	def evaluate_model(self, dataset):
		# Iterate over the dataset
		tot_dice = 0
		tot_acc = 0
		count= 0
		accuracy_func =  Utils.multi_class_dice_coefficient
		print(tf.data.experimental.cardinality(dataset).numpy())
		for batch_images,batch_class,batch_masks in dataset:
			# Add batch dimension to single images if needed
			batch_masks = batch_masks.numpy()
			batch_images = batch_images.numpy()
			batch_class = batch_class.numpy()
			for i in range(batch_masks.shape[0]):
				inpt = tf.convert_to_tensor(batch_images[i])
				clas = tf.convert_to_tensor(batch_class[i])
				pred_masks = self.feed(inpt, clas)
				
				acc_per_img = accuracy_func(batch_masks[i],Utils.one_hot_vec(pred_masks))
				tot_dice += acc_per_img
				count+=1
		return tot_dice/count