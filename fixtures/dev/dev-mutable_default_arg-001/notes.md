# dev-mutable_default_arg-001

**Category:** mutable_default_arg · **Module:** `tabular.py` · **Reference fix:** 3 changed line(s)

A default argument is evaluated once, when the function is defined. The first call looks perfectly correct, which is what makes this defect interesting: only the second call can reveal it.

> This file is never placed in a model prompt.
