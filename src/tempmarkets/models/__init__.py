"""Predictive-distribution models for the integer °F settlement max.

Every model returns a `Forecast`: a probability mass over integers
center + OFFSETS, with center = round(NBM txn). Tails beyond the window are
folded into the end bins, so each row sums to 1.
"""
