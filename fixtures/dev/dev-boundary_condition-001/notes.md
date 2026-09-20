# dev-boundary_condition-001

**Category:** boundary_condition · **Module:** `retry.py` · **Reference fix:** 1 changed line(s)

An off-by-one at a limit check. In production this shape of defect costs one extra request per failing call, which is invisible until it is not.

> This file is never placed in a model prompt.
