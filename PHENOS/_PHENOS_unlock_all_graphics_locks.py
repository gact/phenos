#!/usr/bin/env python -tt
# -*- coding: utf-8 -*-
"""
"""

################################################################################

import os, sys
from phenos import *
import logging

################################################################################

filename = os.path.basename(__file__)
authors = ("Dave B. H. Barton")
version = "0.1"

global LOG
LOG=logging.getLogger()
LOGLEVEL=logging.INFO#DEBUG
#
if __name__=="__main__":
    setup_logging()
    sys.excepthook=log_uncaught_exceptions

    for cf in CombiFiles():
        cf.unlock()
        LOG.info("unlocked allprocessed for {}".format(cf.value))
    answer=raw_input("Hit ENTER to close")

