#!/usr/bin/env python -tt
# -*- coding: utf-8 -*-
"""
"""

################################################################################

import os, sys
from phenos import *
from collections import defaultdict

################################################################################

filename = os.path.basename(__file__)
authors = ("Dave B. H. Barton")
version = "0.1"
#

if __name__=="__main__":
    setup_logging("INFO")
    sys.excepthook=log_uncaught_exceptions

    DBase.autobackup=False

    SD=defaultdict(list)
    for cr in CombiReadings():
        st=cr["strain"].value
        pm=cr["platedmass"].value
        SD[st].append(pm)

    print SD

