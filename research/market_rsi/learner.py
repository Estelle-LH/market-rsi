"""Small dependency-free logistic adapter, not the missing historical baseline."""
import math
import time


def sigmoid(x):
    return 1 / (1 + math.exp(-max(-40, min(40, x))))


def fit_predict(config, train, evaluation):
    start = time.monotonic()
    names = sorted(train[0]["features"])
    steps = config.get("steps", 30)
    lr, l2 = float(config.get("learning_rate", 0.1)), float(config.get("l2", 0.01))
    if not isinstance(steps, int) or isinstance(steps, bool) or not 1 <= steps <= 1000:
        raise ValueError("steps must be 1..1000")
    if not math.isfinite(lr) or not 0 < lr <= 2 or not math.isfinite(l2) or not 0 <= l2 <= 10:
        raise ValueError("invalid optimizer settings")
    n = len(train)
    checkpoint = config.get("initial_checkpoint")
    if checkpoint:
        if checkpoint["features"] != names:
            raise ValueError("parent feature schema changed")
        means, scales, weights = checkpoint["means"], checkpoint["scales"], checkpoint["weights"][:]
        prior_steps = checkpoint["cumulative_optimizer_steps"]
    else:
        means = [sum(r["features"][f] for r in train) / n for f in names]
        scales = [max(1e-8, math.sqrt(sum((r["features"][f] - mu) ** 2 for r in train) / n))
                  for f, mu in zip(names, means)]
        weights, prior_steps = [0.0] * (len(names) + 1), 0
    if config.get("frozen_parent"):
        if checkpoint is None:
            raise ValueError("frozen parent requires an actual checkpoint")
        steps = 0

    def vector(row):
        return [1.0] + [(row["features"][f] - mu) / scale for f, mu, scale in zip(names, means, scales)]

    x, y = [vector(r) for r in train], [r["label"] for r in train]
    for _ in range(steps):
        gradient = [0.0] * len(weights)
        for row, target in zip(x, y):
            error = sigmoid(sum(a * b for a, b in zip(weights, row))) - target
            for j, value in enumerate(row):
                gradient[j] += error * value / n
        weights = [w - lr * (g + (l2 * w if j else 0)) for j, (w, g) in enumerate(zip(weights, gradient))]
    predictions = {r["row_id"]: sigmoid(sum(a * b for a, b in zip(weights, vector(r)))) for r in evaluation}
    checkpoint = dict(features=names, means=means, scales=scales, weights=weights,
                      cumulative_optimizer_steps=prior_steps + steps)
    return predictions, dict(checkpoint=checkpoint, optimizer_steps=steps, training_rows=n,
                              elapsed_seconds=time.monotonic() - start, new_external_charge_usd="0",
                              external_charge_scope="local adapter has no provider calls; excludes subscription and hardware")
