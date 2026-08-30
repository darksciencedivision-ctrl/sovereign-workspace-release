"""EPC-01 P1-5. This file makes `tests.support` a REGULAR package.

It is empty of code on purpose. Before it existed, `modules/sow/tests` was a namespace
package while `modules/distillery/tests` was a regular one, and a regular package always
wins the import search regardless of sys.path order — so in a whole-product run from the
repository root, SOW's `from tests.support import ...` bound to distillery's package and
eleven test modules failed to collect. Making both regular lets sys.path order decide, and
the repository-root conftest puts modules/sow first.
"""
