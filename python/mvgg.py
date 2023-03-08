import os
from typing import Optional
import nengo
import numpy as np
import matplotlib.pyplot as plt
from scipy.stats import multivariate_normal
from TouchDataset import TouchDataset
from nengo_extras.plot_spikes import (
    plot_spikes,
)

_DATAPATH = os.path.join(os.path.dirname(__file__), "../data/touch.pkl")
_IMAGE_DIM: Optional[int] = None

# Prepare dataset
dataset = TouchDataset(_DATAPATH, noise_scale=0.1, scope=(-1.0, 1.0))
X_train, y_train, X_test, y_test = dataset.split_set(ratio=0.5, shuffle=True)
_IMAGE_DIM = X_train[0].shape[0]

# Simulation parameters
dt = 1e-3
max_rates = 200
n_mean = 10
n_hidden = 4
n_output = 36
n_steps = 500
sigma = 1

ens_params = dict(radius=1, intercepts=nengo.dists.Gaussian(0, 0.1))
conn_config = dict(
    learning_rule_type=nengo.BCM(1e-5),
    synapse=dt,
)


def gen_gaussian_weights(mean, cov, size):
    x, y = np.meshgrid(np.arange(size), np.arange(size))
    pos = np.dstack((x, y))
    rv = multivariate_normal(mean, cov)
    pdf = rv.pdf(pos)
    pdf /= np.sum(pdf)
    sample = np.random.choice(
        size * size, p=pdf.ravel(), size=size * size // (n_hidden * n_hidden) + 1
    )
    M = np.zeros(size * size)
    M[sample] = 1
    return M


def gen_mean_weights(direction: int, size: int) -> np.ndarray:
    """Return the weights to compute mean for 2D input of size x size.

    Args:
        direction (int): 0 for y-axis and 1 for x-axis.
        size (int): Size of the weight matrix.

    Returns:
        np.ndarray: Weight matrix of dimension size x size.
    """
    x = np.arange(size)
    M = np.repeat(x[:, np.newaxis], size, axis=1)

    return M if direction == 0 else M.T


def input_func(t):
    index = int(t / (dt * n_steps))
    return X_train[index].ravel()


def output_func(t):
    index = int(t / (dt * n_steps))
    theta = y_train[index]
    n = np.floor(theta / np.pi)
    return (theta - n * np.pi) / np.pi * 180


# Create the Nengo model
with nengo.Network(label="mvgg") as model:
    truth = nengo.Node(output_func)

    # Create input layer
    stim = nengo.Node(input_func)
    inp = nengo.Ensemble(
        n_neurons=stim.size_out,
        dimensions=1,
        max_rates=nengo.dists.Choice([max_rates]),
        neuron_type=nengo.AdaptiveLIF(),
        label="inp",
        **ens_params
    )
    conn_stim2inp = nengo.Connection(stim, inp.neurons, transform=1, synapse=None)

    # Create hidden layer
    hidden = nengo.Ensemble(
        n_neurons=n_hidden * n_hidden,
        dimensions=1,
        neuron_type=nengo.LIF(),
        label="hidden",
        **ens_params
    )
    weights = np.empty((hidden.n_neurons, inp.n_neurons))
    stride = (_IMAGE_DIM - n_hidden) // (n_hidden + 1)
    for i in range(n_hidden):
        for j in range(n_hidden):
            weight = gen_gaussian_weights(
                [(i + 1) * (stride + 1) - 1, (j + 1) * (stride + 1) - 1],
                [[sigma * sigma, 0], [0, sigma * sigma]],
                _IMAGE_DIM,
            )
            weights[i * n_hidden + j, :] = weight.ravel()
    conn_inp2hidden = nengo.Connection(inp.neurons, hidden.neurons, transform=weights)

    # Create WTA layer
    wta = nengo.Ensemble(
        n_neurons=n_output,
        dimensions=1,
        radius=2,
        intercepts=nengo.dists.Gaussian(0, 0.1),
        label="wta",
    )
    conn_hidden2wta = nengo.Connection(
        hidden,
        wta.neurons,
        solver=nengo.solvers.LstsqL2(weights=True),
        transform=np.random.random((wta.n_neurons, hidden.dimensions)),
        label="hidden2out",
        **conn_config
    )
    conn_wta2wta = nengo.Connection(
        wta,
        wta,
        transform=np.eye(wta.dimensions) - np.ones((wta.dimensions, wta.dimensions)),
    )

    # Create output layer
    out = nengo.Ensemble(
        n_neurons=inp.n_neurons, dimensions=1, label="out", **ens_params
    )
    conn_wta2out = nengo.Connection(
        wta.neurons,
        out.neurons,
        transform=nengo.dists.Gaussian(0, 5),
        label="wta2out",
        learning_rule_type=nengo.PES(1e-5),
    )

    # Create error ensemble
    error = nengo.Ensemble(
        n_neurons=inp.n_neurons, dimensions=1, label="error", **ens_params
    )
    conn_inp2error = nengo.Connection(
        inp.neurons, error.neurons, transform=-1, synapse=None, label="conn_inp2error"
    )
    conn_out2error = nengo.Connection(out.neurons, error.neurons, synapse=None)

    # Connect learning rules
    nengo.Connection(error, conn_wta2out.learning_rule)

    # Create probes
    inp_p = nengo.Probe(inp, synapse=0.01)
    wta_p = nengo.Probe(wta, synapse=0.01)
    weights_p = nengo.Probe(conn_hidden2wta, "weights", synapse=0.01)

with nengo.Simulator(model) as sim:
    sim.run(2.0)


plt.imshow(gen_mean_weights(0, _IMAGE_DIM))
# plt.plot(sim.trange(), sim.data[weights_p][..., n_hidden])
plt.show()
