#!/usr/bin/env python -tt
# -*- coding: utf-8 -*-
"""
Works out what folder it's in, what the database name should be,
and calls the primary functions with that information
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
    setup_logging()
    sys.excepthook=log_uncaught_exceptions

    CR=CombiReadings()
    ST=Strains()

    folder=os.path.dirname(ST[0].get_graphicspath())
    LOG.info("beginning strain plots for {}".format(folder))
    prepare_path(folder)
    output=curveplot_allstrains(CR,ST)
    open_on_Windows(folder)
    LOG.info("completed {} strain plots for {}".format(output,folder))
