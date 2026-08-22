"""Offline projection engine for draft-day player valuation.

A fantasy basketball draft happens before any games of the new season are played,
so the in-season analytics in :mod:`tools.player` have no input. This package
produces forward-looking per-game stat lines from historical box scores, exported
as a CSV that the draft assistant imports.

Nothing in the live draft path depends on how the CSV was produced, so the model
never runs during a draft.
"""
