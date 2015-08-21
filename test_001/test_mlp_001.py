__author__ = 'msei'

import math
import numpy as np

import theano
import theano.tensor as T

import time

import lasagne

import traindata_mix

print "Preparing data..."

# prepare data
complete_x = list()
complete_y = list()

for position, fft, c in traindata_mix.test_data_iterator(traindata_mix.RING_01_TEST_DATA):
    complete_x.append([[fft]])
    complete_y.append(c)

num_epochs = 3000
mini_batch_size = 20000

complete_x_len = len(complete_x)

end_part_1 = int(math.floor(complete_x_len / 2.0))

start_part_2 = int(math.floor(complete_x_len / 4.0)) * 2
end_part_2 = int(math.floor(complete_x_len / 4.0)) * 3

start_part_3 = int(math.floor(complete_x_len / 4.0)) * 3
end_part_3 = complete_x_len

X_train = np.array(complete_x[0:end_part_1])
y_train = np.array(complete_y[0:end_part_1], dtype=np.uint8)

X_val = np.array(complete_x[start_part_2:end_part_2])
y_val = np.array(complete_y[start_part_2:end_part_2], dtype=np.uint8)

X_test = np.array(complete_x[start_part_3:end_part_3])
y_test = np.array(complete_y[start_part_3:end_part_3], dtype=np.uint8)

# count how many true samples are in each set
y_train_true = 0
y_val_true = 0
y_test_true = 0

for i in y_train:
    if i > 0:
        y_train_true += 1

for i in y_val:
    if i > 0:
        y_val_true += 1

for i in y_test:
    if i > 0:
        y_test_true += 1

print "len=", complete_x_len, "y_train_true=", y_train_true, "y_val_true=", y_val_true, "y_test_true=", y_test_true

# clear immediate variables
complete_x = None
complete_y = None

print X_train.shape, y_train.shape
# (8000, 1, 1, 2)

print "Preparing theano, lasagne structures..."


def build_mlp(input_var=None):
    # This creates an MLP of two hidden layers of 800 units each, followed by
    # a softmax output layer of 10 units. It applies 20% dropout to the input
    # data and 50% dropout to the hidden layers.

    window_size_half = 128

    # Input layer, specifying the expected input shape of the network
    # (unspecified batchsize, 1 channel, 28 rows and 28 columns) and
    # linking it to the given Theano variable `input_var`, if any:
    l_in = lasagne.layers.InputLayer(shape=(None, 1, 1, window_size_half),
                                     input_var=input_var)

    # Apply 20% dropout to the input data:
    # l_in_drop = lasagne.layers.DropoutLayer(l_in, p=0.2)

    # Add a fully-connected layer of 800 units, using the linear rectifier, and
    # initializing weights with Glorot's scheme (which is the default anyway):
    l_hid_1 = lasagne.layers.DenseLayer(
            l_in, num_units=window_size_half * 5,
            nonlinearity=lasagne.nonlinearities.sigmoid,
            W=lasagne.init.GlorotUniform())

    l_hid_2 = lasagne.layers.DenseLayer(
            l_hid_1, num_units=window_size_half * 5,
            nonlinearity=lasagne.nonlinearities.sigmoid,
            W=lasagne.init.GlorotUniform())

    # Finally, we'll add the fully-connected output layer, of 10 softmax units:
    l_out = lasagne.layers.DenseLayer(
            l_hid_2, num_units=2,
            nonlinearity=lasagne.nonlinearities.softmax)

    # Each layer is linked to its incoming layer(s), so we only need to pass
    # the output layer to give access to a network in Lasagne:
    return l_out

# Prepare Theano variables for inputs and targets
input_var = T.tensor4('inputs')
target_var = T.ivector('targets')

network = build_mlp(input_var)

# Create a loss expression for training, i.e., a scalar objective we want
# to minimize (for our multi-class problem, it is the cross-entropy loss):
prediction = lasagne.layers.get_output(network)
loss = lasagne.objectives.categorical_crossentropy(prediction, target_var)
loss = loss.mean()
# We could add some weight decay as well here, see lasagne.regularization.

# Create update expressions for training, i.e., how to modify the
# parameters at each training step. Here, we'll use Stochastic Gradient
# Descent (SGD) with Nesterov momentum, but Lasagne offers plenty more.
params = lasagne.layers.get_all_params(network, trainable=True)
updates = lasagne.updates.nesterov_momentum(
        loss, params, learning_rate=0.01, momentum=0.9)

# Create a loss expression for validation/testing. The crucial difference
# here is that we do a deterministic forward pass through the network,
# disabling dropout layers.
test_prediction = lasagne.layers.get_output(network, deterministic=True)
test_loss = lasagne.objectives.categorical_crossentropy(test_prediction,
                                                        target_var)
test_loss = test_loss.mean()
# As a bonus, also create an expression for the classification accuracy:
test_acc = T.mean(T.eq(T.argmax(test_prediction, axis=1), target_var),
                  dtype=theano.config.floatX)

# Compile a function performing a training step on a mini-batch (by giving
# the updates dictionary) and returning the corresponding training loss:
train_fn = theano.function([input_var, target_var], loss, updates=updates, allow_input_downcast=True)

# Compile a second function computing the validation loss and accuracy:
val_fn = theano.function([input_var, target_var], [test_loss, test_acc], allow_input_downcast=True)


# ############################# Batch iterator ###############################
# This is just a simple helper function iterating over training data in
# mini-batches of a particular size, optionally in random order. It assumes
# data is available as numpy arrays. For big datasets, you could load numpy
# arrays as memory-mapped files (np.load(..., mmap_mode='r')), or write your
# own custom data iteration function. For small datasets, you can also copy
# them to GPU at once for slightly improved performance. This would involve
# several changes in the main program, though, and is not demonstrated here.

def iterate_minibatches(inputs, targets, batchsize, shuffle=False):
    assert len(inputs) == len(targets)
    if shuffle:
        indices = np.arange(len(inputs))
        np.random.shuffle(indices)

    for start_idx in range(0, len(inputs) - batchsize + 1, batchsize):
        if shuffle:
            excerpt = indices[start_idx:start_idx + batchsize]
        else:
            excerpt = slice(start_idx, start_idx + batchsize)
        yield inputs[excerpt], targets[excerpt]
    else:
        if shuffle:
            excerpt = indices[0:len(inputs)]
        else:
            excerpt = slice(0, len(inputs))
        yield inputs[excerpt], targets[excerpt]


# Finally, launch the training loop.
print("Starting training...")
# We iterate over epochs:
for epoch in range(num_epochs):
    # In each epoch, we do a full pass over the training data:
    train_err = 0
    train_batches = 0
    start_time = time.time()
    for batch in iterate_minibatches(X_train, y_train, mini_batch_size, shuffle=True):
        inputs, targets = batch
        train_err += train_fn(inputs, targets)
        train_batches += 1

    # And a full pass over the validation data:
    val_err = 0
    val_acc = 0
    val_batches = 0
    for batch in iterate_minibatches(X_val, y_val, mini_batch_size, shuffle=True):
        inputs, targets = batch
        err, acc = val_fn(inputs, targets)
        val_err += err
        val_acc += acc
        val_batches += 1

    # Then we print the results for this epoch:
    print("Epoch {} of {} took {:.3f}s".format(
        epoch + 1, num_epochs, time.time() - start_time))
    print("  training loss:\t\t{:.6f}".format(train_err / train_batches))
    print("  validation loss:\t\t{:.6f}".format(val_err / val_batches))
    print("  validation accuracy:\t\t{:.2f} %".format(
        val_acc / val_batches * 100))

    np.savez('test_mlp_001-epoch-' + str(epoch) + '.npz', lasagne.layers.get_all_param_values(network))

# After training, we compute and print the test error:
test_err = 0
test_acc = 0
test_batches = 0
for batch in iterate_minibatches(X_test, y_test, mini_batch_size, shuffle=True):
    inputs, targets = batch
    err, acc = val_fn(inputs, targets)
    test_err += err
    test_acc += acc
    test_batches += 1
print("Final results:")
print("  test loss:\t\t\t{:.6f}".format(test_err / test_batches))
print("  test accuracy:\t\t{:.2f} %".format(
    test_acc / test_batches * 100))

# Optionally, you could now dump the network weights to a file like this:
# np.savez('model.npz', lasagne.layers.get_all_param_values(network))

np.savez('test_mlp_001-final.npz', lasagne.layers.get_all_param_values(network))
