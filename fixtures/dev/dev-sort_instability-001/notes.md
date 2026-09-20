# dev-sort_instability-001

**Category:** sort_instability · **Module:** `sorting.py` · **Reference fix:** 1 changed line(s)

Successive stable sorts must run from the least significant key to the most significant. Reversing that inverts key precedence. When both keys happen to agree on an ordering the output is identical, which hides it.

> This file is never placed in a model prompt.
