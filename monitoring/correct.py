"""Bias-corrected failure prevalence for a monitoring period."""

from __future__ import annotations

from typing import Any, Sequence

import numpy as np


def _rates(labels: np.ndarray, preds: np.ndarray) -> tuple[float, float] | None:
    """Failure sensitivity and pass specificity, or None if a class is absent."""
    positive = labels == 1
    negative = labels == 0
    if not positive.any() or not negative.any():
        return None
    sensitivity = float(preds[positive].mean())
    specificity = float(1.0 - preds[negative].mean())
    return sensitivity, specificity


def corrected_mode_prevalence(
    sample_preds: Sequence[int],
    test_labels: Sequence[int],
    test_preds: Sequence[int],
    confidence: float = 0.95,
    bootstrap_iterations: int = 20000,
    seed: int | None = 7,
) -> dict[str, Any]:
    """Bias-corrected live prevalence for one mode from sampled verdicts.

    The contract, precisely:

      1. ``raw`` is the uncorrected flag rate: ``mean(sample_preds)``.
      2. Compute the frozen judge's failure sensitivity and pass specificity
         from ``test_labels`` and ``test_preds``. Both use the monitoring
         convention that 1 means a failure is present. Failure sensitivity is
         the flagged fraction of human-labeled failures. Pass specificity is
         the unflagged fraction of human-labeled passes.
      3. Compute the Rogan-Gladen point estimate, then resample the held-out
         records and sampled predictions to obtain a percentile-bootstrap
         interval. Use a seeded NumPy generator so the committed result is
         reproducible.
      4. Resample the monitoring predictions and the paired held-out records
         independently with replacement. Keep their original sample sizes.
         Discard a draw if the correction cannot be computed. Clamp each
         retained estimate to [0, 1], then take the percentile interval.
         Raise ``ValueError`` if no replicate is valid.

    Args:
        sample_preds: the judge's 0/1 verdicts over the UNIFORM BASE sample
            only (never the risk strata; they are biased toward failure by
            design).
        test_labels: human labels for the frozen Homework 5 judge's test
            split.
        test_preds: the frozen judge's predictions on that test split.
        confidence: interval confidence level.
        bootstrap_iterations: number of percentile-bootstrap replicates.
        seed: numpy seed for a reproducible interval; None leaves the RNG
            untouched.

    Returns:
        {"raw", "corrected", "ci_low", "ci_high", "confidence",
         "failure_sensitivity", "pass_specificity", "n_sample"}
        with "corrected" clamped to [0, 1] and rates rounded to 4 places.

    Raises:
        ValueError: if an input is empty, the held-out inputs have different
            lengths, a value is not 0 or 1, a class is absent, the judge is
            missing a usable correction, or no bootstrap replicate is valid.
    """
    sample_preds = list(sample_preds)
    test_labels = list(test_labels)
    test_preds = list(test_preds)

    if not sample_preds or not test_labels:
        raise ValueError("sample_preds and test_labels must be non-empty")
    if len(test_labels) != len(test_preds):
        raise ValueError("test_labels and test_preds must have the same length")
    for value in (*sample_preds, *test_labels, *test_preds):
        if value not in (0, 1):
            raise ValueError("every prediction and label must be 0 or 1")

    labels_arr = np.asarray(test_labels)
    preds_arr = np.asarray(test_preds)
    sample_arr = np.asarray(sample_preds)

    point_rates = _rates(labels_arr, preds_arr)
    if point_rates is None:
        raise ValueError("test_labels must contain both classes")
    sensitivity, specificity = point_rates
    denom = sensitivity + specificity - 1
    if denom == 0:
        raise ValueError("judge is missing a usable correction (Se + Sp - 1 == 0)")

    raw = float(sample_arr.mean())
    corrected_point = (raw - (1 - specificity)) / denom
    corrected_point = min(1.0, max(0.0, corrected_point))

    rng = np.random.default_rng(seed)
    n_sample = len(sample_arr)
    n_test = len(labels_arr)
    estimates: list[float] = []
    for _ in range(bootstrap_iterations):
        sample_idx = rng.integers(0, n_sample, size=n_sample)
        test_idx = rng.integers(0, n_test, size=n_test)
        rates = _rates(labels_arr[test_idx], preds_arr[test_idx])
        if rates is None:
            continue
        sens_b, spec_b = rates
        denom_b = sens_b + spec_b - 1
        if denom_b == 0:
            continue
        ap_b = float(sample_arr[sample_idx].mean())
        estimate = (ap_b - (1 - spec_b)) / denom_b
        estimates.append(min(1.0, max(0.0, estimate)))

    if not estimates:
        raise ValueError("no valid bootstrap replicate; the judge correction is unstable")

    alpha = 1 - confidence
    ci_low, ci_high = np.percentile(estimates, [100 * alpha / 2, 100 * (1 - alpha / 2)])

    return {
        "raw": round(raw, 4),
        "corrected": round(corrected_point, 4),
        "ci_low": round(float(ci_low), 4),
        "ci_high": round(float(ci_high), 4),
        "confidence": confidence,
        "failure_sensitivity": round(sensitivity, 4),
        "pass_specificity": round(specificity, 4),
        "n_sample": n_sample,
    }
