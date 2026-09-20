# holdout-off_by_one-001

**Category:** off_by_one · **Module:** `paging.py` · **Reference fix:** 1 changed line(s)

Shortening the range by one only changes the result when the last page is partial, so evenly divisible inputs look correct.

> This file is never placed in a model prompt.
