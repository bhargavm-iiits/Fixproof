# holdout-early_return-001

**Category:** early_return · **Module:** `intervals.py` · **Reference fix:** 1 changed line(s)

Needs three or more disjoint spans to show at all: with two, returning after appending the second is the same as falling through. The failure surfaces two layers away, in subtraction rather than in merging.

> This file is never placed in a model prompt.
