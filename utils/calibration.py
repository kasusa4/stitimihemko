# utils/calibration.py
from collections import defaultdict

class ConfidenceCalibrator:
    """
    Maps model confidence to actual win-rate using historical data.
    E.g., if picks at 70% actually win 58%, we adjust the displayed confidence to 58%.
    """
    def __init__(self, n_bins=10):
        self.bins = defaultdict(lambda: {'predictions': 0, 'wins': 0})
        self.n_bins = n_bins
        self.calibration_table = {}

    def log(self, confidence, won):
        bin_idx = min(int(confidence * self.n_bins), self.n_bins - 1)
        self.bins[bin_idx]['predictions'] += 1
        if won:
            self.bins[bin_idx]['wins'] += 1

    def build_table(self):
        for bin_idx, stats in self.bins.items():
            if stats['predictions'] >= 10:
                actual = stats['wins'] / stats['predictions']
                lower = bin_idx / self.n_bins
                upper = (bin_idx + 1) / self.n_bins
                self.calibration_table[(lower, upper)] = actual

    def calibrate(self, raw_confidence):
        """Return calibrated confidence based on historical performance."""
        if not self.calibration_table:
            return raw_confidence
        for (lo, hi), actual in self.calibration_table.items():
            if lo <= raw_confidence < hi:
                return actual
        return raw_confidence