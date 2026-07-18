"""Review-flows package: the shared due-cards query and review/grading routes.

Ticket 09's single load-bearing design choice lives in ``queries.py``:
``get_due_cards`` is the *only* place "what's due" is computed, used by both
the global daily review and the per-subject review routes in ``routes.py`` --
this is what makes grading in one view provably visible in the other rather
than relying on convention.
"""
