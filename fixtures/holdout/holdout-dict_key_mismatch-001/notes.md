# holdout-dict_key_mismatch-001

**Category:** dict_key_mismatch · **Module:** `parsing.py` · **Reference fix:** 1 changed line(s)

Rendering still works, because rendering only reads the table and never looks a token up in it. Only the parse direction fails.

> This file is never placed in a model prompt.
