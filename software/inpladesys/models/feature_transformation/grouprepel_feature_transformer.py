import numpy as np
import tensorflow as tf
from inpladesys.models.feature_transformation.abstract_feature_transformer import \
    AbstractFeatureTransformer
from typing import List
from inpladesys.datatypes import Dataset


class GroupRepelFeatureTransformer(AbstractFeatureTransformer):
    def __init__(self,
                 output_dimension,
                 reinitialize_on_fit,
                 input_dimension=None,
                 nonlinear_layer_count=0,
                 nonlinearity=tf.nn.tanh,
                 a = 0.5,
                 learning_rate=1e-3,
                 iteration_count=10000,
                 regularization=1,
                 verbose=False,
                 random_state=None):
        self.iteration_count = iteration_count
        self.reinitialize_on_fit = reinitialize_on_fit
        self.initialized = False

        self.x, self.labels, self.y = [None] * 3
        self.train_step_nd, self.loss_nd = [None] * 2

        self.a=a

        def initialize(input_dimension):
            self.graph = tf.Graph()
            with self.graph.as_default():
                if random_state is not None:
                    tf.set_random_seed(random_state)
                self.sess = tf.Session()
                self._build_graph(input_dimension, output_dimension,
                                  nonlinear_layer_count, nonlinearity,
                                  learning_rate, regularization)
            self._build_graph_if_not_built = lambda x: None

        self._build_graph_if_not_built = lambda input_dim: initialize(input_dim)

        if input_dimension is not None:
            initialize(input_dimension)

        self.verbose = verbose

    def fit(self, X: List[np.ndarray], G: List[np.ndarray]):
        self._build_graph_if_not_built(X[0].shape[1])
        assert (len(X) == len(G))
        with self.graph.as_default():
            if self.reinitialize_on_fit or not self.initialized:
                self.sess.run(tf.global_variables_initializer())
                self.initialized = True
            ds = Dataset(X[:], G[:])
            ravg_cost = 0.0;
            a = 10
            for i in range(self.iteration_count):
                ds.shuffle()
                costs = []
                for x, labels in ds:
                    fetches = [self.train_step_nd, self.loss_nd, self.y]
                    feed_dict = {self.x: x, self.labels: labels}
                    _, cost, y = self.sess.run(fetches, feed_dict)
                    costs.append(cost)
                    if self.verbose:
                        print(cost)
                cavg_cost = np.average(costs)
                if i == 0:
                    ravg_cost = cavg_cost
                else:
                    ravg_cost = (a - 1) / a * ravg_cost + 1 / a * cavg_cost
                print("\r{}/{}, ~error: {:.3f} ({:.3f})".format(i + 1, self.iteration_count, ravg_cost, cavg_cost),
                      end='')
            print('')

    def transform(self, X: List[np.ndarray]) -> List[np.ndarray]:
        self._build_graph_if_not_built(X[0].shape[1])
        return [self.sess.run([self.y], {self.x: x})[0] for x in X]

    def _build_graph(self, x_dim, y_dim, nonlinear_layer_count, nonlinearity, learning_rate, regularization):
        def distance(a, b):
            return (a - b) ** 2

        #def cdistance(a, b):
        #    return a*b

        def fc(in_size: int, out_size: int):
            w = tf.Variable(tf.truncated_normal([in_size, out_size], 0, 0.1))
            r_params.append(w)
            return w

        def bias(size: int):
            return tf.Variable(tf.truncated_normal([size], 0, 0.0))

        r_params = []

        def transform(x):
            nlc = nonlinear_layer_count
            h = 1
            w=[]
            if nlc == 0:
                w = [fc(x_dim, y_dim)]
                x = tf.matmul(x, w[0])
            else:
                w = [fc(x_dim, h * x_dim)]
                w += [fc(h * x_dim, h * x_dim) for i in range(nlc - 1)]
                b = [bias(h * x_dim)]
                b += [bias(h * x_dim) for i in range(nlc - 1)]
                for wi, bi in zip(w, b):
                    x = nonlinearity(tf.matmul(x, wi) + bi)
                x = tf.matmul(x, fc(h * x_dim, y_dim))
            nonlocal r_params
            r_params = w
            return x

        def fori(istart, istop, body, body_var, shape_invar=None):
            #if type(istart) == int:
            #    istart = tf.constant(istart)
            #if type(istop) == int:
            #    istop = tf.constant(istop)
            if shape_invar is not None:
                shape_invar = [tf.TensorShape([]), shape_invar]
            return tf.while_loop(
                lambda i, b: tf.less(i, istop),
                lambda i, b: (i + 1, body(i, b)),
                [istart, body_var],
                shape_invar
            )[1]

        def extract_group(y, labels, label):
            indices = tf.reshape(tf.where(tf.equal(labels, label)), [-1])
            return tf.gather(y, indices)

        def get_centroids(y, labels, centroid_count):
            def centroid(i):
                return tf.reshape(tf.reduce_mean(extract_group(y, labels, i), axis=0), [1, y_dim])

            return fori(1, centroid_count,
                        lambda i, c: tf.concat([c, centroid(i)], axis=0),
                        centroid(0), tf.TensorShape([None, y_dim]))

        def get_group_loss(y, labels, centroids, centroid_count):
            def loss(i):
                group = extract_group(y, labels, i)
                return tf.reduce_mean(distance(group, centroids[i]))

            return fori(0, centroid_count, lambda i, e: e + loss(i), tf.constant(.0))

        def get_centroid_loss(centroids, centroid_count):
            def get_part(i):
                dists = distance(centroids[i + 1:, :], centroids[i, :])
                return tf.reduce_sum(1 / tf.reduce_sum(dists, axis=1))

            n = tf.cast(centroid_count, tf.float32)
            return fori(0, centroid_count - 1, lambda i, e: e + get_part(i), tf.constant(.0)) / n

        # Inputs
        x = tf.placeholder(tf.float32, shape=[None, x_dim])
        labels = tf.placeholder(tf.int32, shape=[None])

        # Output
        y = transform(x)

        # Training
        centroid_count = tf.reduce_max(labels) + 1
        centroids = get_centroids(y, labels, centroid_count)

        group_loss = get_group_loss(y, labels, centroids, centroid_count)
        centroid_loss = get_centroid_loss(centroids, centroid_count)
        r_loss = sum(tf.reduce_mean(p ** 2) for p in r_params)

        group_loss = self.a * group_loss + 1e-6
        centroid_loss = (1 - self.a) * centroid_loss + 1e-6
        loss = centroid_loss + group_loss #+ 0.5*r_loss  # +
        # 0.2 * tf.reduce_mean(tf.reduce_sum(centroids**2, axis=1)) + r_loss
        # loss = 1/(1/group_loss + 1/centroid_loss)

        #optimizer = tf.train.RMSPropOptimizer(learning_rate=learning_rate, decay=0.9)
        optimizer = tf.train.RMSPropOptimizer(learning_rate=learning_rate, decay=0.9)
        train_step = optimizer.minimize(loss)

        # Variables for evaluation
        self.x, self.labels = x, labels
        self.y = y
        self.train_step_nd, self.loss_nd = train_step, loss
        self.centroids = centroids


"""if __name__ == "__main__":
    vectors = np.array(
        [[-1, 1, 1],
         [-1, 1, 1],
         [-1, 1, 1],
         [1, 2, 0],
         [1, 0, 2],
         [5, -2, 5],
         [6, 2, 4],
         [3, 0, 3],
         [3, -3, -2],
         [4, 2, -2],
         [0, 2, 0],
         [0, -5, 0],
         [0, -2, 0]],
        dtype=np.float)
    labels = np.array([0, 0, 0, 1, 1, 2, 2, 3, 3, 3, 4, 4, 4])

    cpn = GroupRepelFeatureTransformer(3, 2, iteration_count=100)

    result = cpn.fit([vectors], [labels])

    print(result[:, 0], result[:, 1])

    import matplotlib.pyplot as plt
    plt.scatter(result[:, 0], result[:, 1])
    plt.show()"""
