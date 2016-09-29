#!/usr/bin/env python -tt
# -*- coding: utf-8 -*-
"""
"""

################################################################################

import os, sys, string
from phenos import *
import tkFileDialog

################################################################################

filename = os.path.basename(__file__)
authors = ("Dave B. H. Barton")
version = "0.1"
#
LOCS=Locations()


def Files_diagnostic(dbasenameroot):
    #check quantities add up
    F=Files(dbasenameroot)
    nfiles=len(F)
    nfilesreadings=F.total()
    filescombifiles=F.get_values_of_atom("combifile")
    R=Readings(dbasenameroot)
    nreadings=len(R)
    if nfilesreadings!=nreadings:
        LOG.warning("Files({}) has {} files that should "
                    "have {} readings\n"
                    "but Readings({}) has {} readings\n"
                    .format(dbasenameroot,nfiles,nfilesreadings,
                            dbasenameroot,nreadings))

    CF=CombiFiles(dbasenameroot)
    ncfiles=len(CF)
    ncfilesreadings=CF.total()
    CR=CombiReadings(dbasenameroot)
    ncreadings=len(CR)
    if ncfilesreadings!=ncreadings:
        LOG.warning("CombiFiles({}) has {} combifiles that should "
                    "have {} combireadings\n"
                    "CombiReadings({}) has {} combireadings\n"
                    .format(dbasenameroot,ncfiles,ncfilesreadings,
                            dbasenameroot,ncreadings))

    LOG.info("_"*30)
             

if __name__=="__main__":
    setup_logging("INFO")
    sys.excepthook=log_uncaught_exceptions

    for dp in Locations().datpaths:
        Files_diagnostic(os.path.basename(dp))
        



