# dev-off_by_one-001

**Category:** off_by_one · **Module:** `paging.py` · **Reference fix:** 1 changed line(s)

The classic ceiling-division mistake. It is invisible for every input that does *not* divide evenly, which is why a single well-chosen test is worth more here than a dozen random ones.

> This file is never placed in a model prompt.
