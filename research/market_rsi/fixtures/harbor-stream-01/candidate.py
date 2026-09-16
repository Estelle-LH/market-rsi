"""Human-written integration fixture, not a learned market strategy."""
def fit(train, feature_names):
    return sum(row["target"] for row in train) / len(train)


def predict(model, row):
    return model + row["features"]["x"]
