#!/usr/bin/env python -tt
# -*- coding: utf-8 -*-

from setuptools import setup, find_packages
import os

#PHENOS2
"""

"""

def check_directories():
    """
    Ensure all expected directories (and set-up files) are present and correct.
    Create any paths that are missing.
    """
    expected_directories=["DAT files",
                          "Genotypes",
                          "Layouts",
                          "Logs",
                          "Plots",
                          "rQTL input",
                          "Stinger files"]
    for ed in expected_directories:
        if not os.path.exists(ed):
            #logging.info("Directory '{}' not found.".format(ed))
            os.mkdir(ed)
            #logging.info("Directory '{}' created.".format(ed))

check_directories()

with open('README.rst') as f:
    readme = f.read()

with open('LICENSE') as f:
    license = f.read()

setup(name='phenos',
      version='0.2.0',
      description='tools for handling solid media phenotyping data',
      long_description=readme,
      author='David B. H. Barton',
      author_email='dbh8@leicester.ac.uk',
      url='',
      license=license,
      packages=find_packages(exclude=('tests', 'docs')))

