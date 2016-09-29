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
    setup_logging("INFO")
    sys.excepthook=log_uncaught_exceptions

    DBase.autobackup=True

    Files().update()
    PlateLayouts().update()
    CombiFiles().update()
    CombiFiles().analyze(export=True,
                         rqtl=False,
                         illustrate=True)
    #ControlledExperiments().update(**kwargs)
    #ControlledExperiments().analyze(**kwargs)
    answer=raw_input("Hit ENTER to close")

