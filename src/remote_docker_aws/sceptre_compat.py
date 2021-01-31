"""
This is to avoid the fractions.gcd import done in networkx (used by sceptre)

Once this issue is resolved https://github.com/Sceptre/sceptre/issues/942
we can update sceptre and remove this logic
"""
import fractions

try:
    fractions.gcd
except AttributeError:
    from math import gcd

    setattr(fractions, "gcd", gcd)

from sceptre.cli.helpers import setup_logging  # noqa
from sceptre.context import SceptreContext  # noqa
from sceptre.plan.plan import SceptrePlan  # noqa
