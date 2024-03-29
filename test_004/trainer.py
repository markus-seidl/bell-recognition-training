__author__ = 'msei'
import math
import numpy as np
import theano
import theano.tensor as T
import sys
import pickle
import time
import lasagne
import logging


class Configuration:
    network = ConfigurationNetwork()
    fft = ConfigurationFFT()
    training = ConfigurationTraining()


class ConfigurationNetwork:
    pass


class ConfigurationTraining:
    def __init__(self):
        self.num_epochs = 100
        self.num_training_size = 200


class ConfigurationFFT:
    def __init__(self):
        self.size = 256


class TrainerV1:
    def __init__(self):
        # TODO load configuration
        self.configuration = Configuration()
        self.log = logging.getLogger(__name__)

    def prepare_data(self):
        pass

    def build_mlp(self, input_var):
        # This creates an MLP of two hidden layers of 800 units each, followed by
        # a softmax output layer of 10 units. It applies 20% dropout to the input
        # data and 50% dropout to the hidden layers.

        window_size = self.configuration.fft.size

        # Input layer, specifying the expected input shape of the network
        # (unspecified batchsize, 1 channel, 28 rows and 28 columns) and
        # linking it to the given Theano variable `input_var`, if any:
        l_in = lasagne.layers.InputLayer(shape=(None, 1, 1, window_size * 2),
                                         input_var=input_var)

        # Apply 20% dropout to the input data:
        # l_in_drop = lasagne.layers.DropoutLayer(l_in, p=0.2)

        # Add a fully-connected layer of 800 units, using the linear rectifier, and
        # initializing weights with Glorot's scheme (which is the default anyway):
        l_hid_1 = lasagne.layers.DenseLayer(
            l_in, num_units=window_size,
            nonlinearity=lasagne.nonlinearities.sigmoid,
            W=lasagne.init.GlorotUniform())

        l_hid_2 = lasagne.layers.DenseLayer(
            l_hid_1, num_units=window_size,
            nonlinearity=lasagne.nonlinearities.sigmoid,
            W=lasagne.init.GlorotUniform())

        # Finally, we'll add the fully-connected output layer, of 10 softmax units:
        l_out = lasagne.layers.DenseLayer(
            l_hid_2, num_units=2,
            nonlinearity=lasagne.nonlinearities.softmax)

        # Each layer is linked to its incoming layer(s), so we only need to pass
        # the output layer to give access to a network in Lasagne:
        return l_out

    def iterate_minibatches(shuffle):
        pass
        # assert len(inputs) == len(targets)
        # if shuffle:
        #     indices = np.arange(len(inputs))
        #     np.random.shuffle(indices)
        #
        # for start_idx in range(0, len(inputs) - batchsize + 1, batchsize):
        #     if shuffle:
        #         excerpt = indices[start_idx:start_idx + batchsize]
        #     else:
        #         excerpt = slice(start_idx, start_idx + batchsize)
        #     yield inputs[excerpt], targets[excerpt]
        # else:
        #     if shuffle:
        #         excerpt = indices[0:len(inputs)]
        #     else:
        #         excerpt = slice(0, len(inputs))
        #     yield inputs[excerpt], targets[excerpt]

    def prepare_theano(self):
        # Prepare Theano variables for inputs and targets
        input_var = T.tensor4('inputs')
        target_var = T.ivector('targets')

        network = self.build_mlp(input_var)

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
        updates = lasagne.updates.nesterov_momentum(loss, params, learning_rate=0.01, momentum=0.9)

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
        train_fn = theano.function([input_var, target_var], loss, updates=updates,
                                   allow_input_downcast=True)

        # Compile a second function computing the validation loss and accuracy:
        val_fn = theano.function([input_var, target_var], [test_loss, test_acc],
                                 allow_input_downcast=True)

        return network, prediction, train_fn, val_fn

    def do_one_epoch(self, prediction, train_fn, val_fn):
        # In each epoch, we do a full pass over the training data:
        train_err = 0
        train_batches = 0
        for batch in self.iterate_minibatches(True):
            inputs, targets = batch
            train_err += train_fn(inputs, targets)
            train_batches += 1

        # And a full pass over the validation data:
        val_err = 0
        val_acc = 0
        val_batches = 0
        for batch in self.iterate_minibatches(True):
            inputs, targets = batch
            err, acc = val_fn(inputs, targets)
            val_err += err
            val_acc += acc
            val_batches += 1

        # And a full custom pass, only to validate what theano functions do
        for batch in self.iterate_minibatches(True):
            inputs, targets = batch
            err, acc = val_fn(inputs, targets)
            val_err += err
            val_acc += acc
            val_batches += 1

        return train_err, train_batches, val_err, val_acc, val_batches

    def run(self):
        self.prepare_data()

        print("Starting training...")

        network, prediction, train_fn, val_fn = self.prepare_theano()
        num_epochs = self.configuration.training.num_epochs
        # We iterate over epochs:
        for epoch_no in range(num_epochs):
            start_time = time.time()
            train_err, train_batches, val_err, val_acc, val_batches = self.do_one_epoch()

            # Then we print the results for this epoch:
            print("Epoch {} of {} took {:.3f}s".format(
                epoch_np + 1, num_epochs, time.time() - start_time))
            print("  training loss:\t\t{:.6f}".format(train_err / train_batches))
            print("  validation loss:\t\t{:.6f}".format(val_err / val_batches))
            print("  validation accuracy:\t\t{:.2f} %".format(
                val_acc / val_batches * 100))

            # np.savez('test_mlp_003-epoch-' + str(epoch) + '.npz', lasagne.layers.get_all_param_values(network))

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
        sys.stdout.flush()

        # Optionally, you could now dump the network weights to a file like this:
        # np.savez('model.npz', lasagne.layers.get_all_param_values(network))

        np.savez('test_mlp_003-final.npz', lasagne.layers.get_all_param_values(network))
