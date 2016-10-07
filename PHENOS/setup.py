#!/usr/bin/env python -tt
# -*- coding: utf-8 -*-

from setuptools import setup, find_packages
import os

#PHENOS
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

#check_directories()

with open('README.rst') as f:
    readme = f.read()

with open('LICENSE') as f:
    license = f.read()

setup(name='phenos',
      version='3.3.0',
      description='tools for handling solid media phenotyping data',
      long_description=readme,
      author='David B. H. Barton',
      author_email='dbh8@leicester.ac.uk',
      url='http://github.com/gact/phenos',
      license=license,
      install_requires=['numpy>=1.9.2',
                        'scipy>=0.16.0c1',
                        'matplotlib>=1.4.3',
                        'tables>=3.2.0',
                        'xlrd>=0.9.3',
                        'brewer2mpl>=1.4.1',
                        'win32com'],
      packages=['phenos'])

