"""Check that TensorFlow Federated works: a hello-world computation, then
five rounds of weighted FedAvg on random data from four fake clients.
Run it inside the TFF environment (see README, section 'TFF environment')."""

import numpy as np
import tensorflow as tf
import tensorflow_federated as tff

print("tff", tff.__version__, "| tf", tf.__version__, "| numpy", np.__version__)


@tff.federated_computation
def hello():
    return "Hello, World!"


print(hello())


def make_client(seed, n=64):
    rng = np.random.default_rng(seed)
    x = rng.normal(size=(n, 8)).astype("float32")
    y = (x[:, 0] + rng.normal(scale=0.3, size=n) > 0).astype("int32")
    return tf.data.Dataset.from_tensor_slices((x, y)).batch(16)


clients = [make_client(s) for s in range(4)]
spec = clients[0].element_spec


def model_fn():
    km = tf.keras.Sequential([tf.keras.layers.Input((8,)),
                              tf.keras.layers.Dense(16, activation="relu"),
                              tf.keras.layers.Dense(2)])
    return tff.learning.models.from_keras_model(
        km, input_spec=spec,
        loss=tf.keras.losses.SparseCategoricalCrossentropy(from_logits=True),
        metrics=[tf.keras.metrics.SparseCategoricalAccuracy()])


process = tff.learning.algorithms.build_weighted_fed_avg(
    model_fn, client_optimizer_fn=tff.learning.optimizers.build_sgdm(learning_rate=0.1))
state = process.initialize()
for r in range(5):
    out = process.next(state, clients)
    state = out.state
    acc = out.metrics["client_work"]["train"]["sparse_categorical_accuracy"]
    print(f"round {r + 1}: train accuracy {float(acc):.3f}")
print("TFF environment OK")
