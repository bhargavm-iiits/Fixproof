# dev-inverted_condition-001

**Category:** inverted_condition · **Module:** `diffstat.py` · **Reference fix:** 1 changed line(s)

Inverting the comparison in a running-maximum loop turns it into a running minimum. Tied inputs still produce the expected answer, so the tie-breaking test keeps passing and only the ordering test fails.

> This file is never placed in a model prompt.
