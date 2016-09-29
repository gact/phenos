#!/usr/bin/env python -tt
# -*- coding: utf-8 -*-
"""
Module notes
"""

#import statements
import os
from .core import *
from .dbtypes import *
from .graphics import *
from .gui import *
from .gui2 import *

################################################################################

filename = os.path.basename(__file__)
authors = ("David Barton")
version = "0.3"


if __name__=="__main__":
    import doctest
    doctest.testmod()
