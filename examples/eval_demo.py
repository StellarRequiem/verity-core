"""A tiny, deterministic 'evaluation' so the proof-carrying example is real and
re-runnable. It computes the accuracy of fixed predictions against fixed labels
and prints it — the number a result-claim would assert. `verity prove` runs this
and checks the claimed value actually matches what comes out.

Deliberately trivial: the point is the *gate*, not the model. Swap this for your
real eval command in your own proofs.jsonl."""

preds  = [1, 0, 1, 1, 0, 1, 0, 0, 1, 0]
labels = [1, 0, 1, 0, 0, 1, 0, 0, 1, 0]   # 9 / 10 correct -> 0.9

acc = sum(p == y for p, y in zip(preds, labels)) / len(labels)
print(f"accuracy: {acc}")
