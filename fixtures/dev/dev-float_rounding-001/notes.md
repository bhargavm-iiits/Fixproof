# dev-float_rounding-001

**Category:** float_rounding · **Module:** `diffstat.py` · **Reference fix:** 1 changed line(s)

Callers that pass an explicit precision are unaffected, so the defect is only visible through the default. Values that happen to be whole numbers also hide it.

> This file is never placed in a model prompt.
