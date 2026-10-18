import sys, time
import numpy as np
import tensorflow as tf

tf.keras.utils.set_random_seed(0)
REPS = int(sys.argv[1]) if len(sys.argv) > 1 else 20

model = tf.keras.Sequential([
    tf.keras.Input(shape=(512,)),
    tf.keras.layers.Dense(1024, activation="relu"),
    tf.keras.layers.Dense(1024, activation="relu"),
    tf.keras.layers.Dense(256, activation="relu"),
    tf.keras.layers.Dense(1, activation="sigmoid"),
])

@tf.function
def score(x):
    return model(x, training=False)

x = tf.constant(np.random.RandomState(0).rand(8192, 512).astype("float32"))
out = score(x).numpy()  # warm-up

t = time.time()
for _ in range(REPS):
    out = score(x).numpy()
dt = time.time() - t
print(f"pairs scored per second: {int(8192 * REPS / dt)}")
print(f"seconds total: {dt:.2f}")
print("first 3 scores:", out[:3, 0])
