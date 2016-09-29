#!/usr/bin/env python -tt
# -*- coding: utf-8 -*-
"""
"""

################################################################################

import os, sys
from phenos import *

################################################################################

filename = os.path.basename(__file__)
authors = ("Dave B. H. Barton")
version = "0.1"
#

if __name__=="__main__":
    #setup_logging("INFO")
    #sys.excepthook=log_uncaught_exceptions

    lastlogpath=Locations().get_last_log(openfolder=True)
    open_on_Windows(lastlogpath)


