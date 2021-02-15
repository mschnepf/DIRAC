#!/usr/bin/env python
########################################################################
# File :    dirac-dms-pfn-accessURL
# Author  : Stuart Paterson
########################################################################
"""
Retrieve an access URL for a PFN given a valid DIRAC SE

Usage:
  dirac-dms-pfn-accessURL [options] ... PFN SE

Arguments:
  PFN:      Physical File Name or file containing PFNs (mandatory)
  SE:       Valid DIRAC SE (mandatory)
"""
from __future__ import print_function
from __future__ import absolute_import
from __future__ import division

__RCSID__ = "$Id$"

import DIRAC
from DIRAC.Core.Base import Script
from DIRAC.Core.Utilities.DIRACScript import DIRACScript


@DIRACScript()
def main():
  Script.parseCommandLine(ignoreErrors=True)
  args = Script.getPositionalArgs()

  if len(args) < 2:
    Script.showHelp(exitCode=1)

  if len(args) > 2:
    print('Only one PFN SE pair will be considered')

  from DIRAC.Interfaces.API.Dirac import Dirac
  dirac = Dirac()
  exitCode = 0

  pfn = args[0]
  seName = args[1]
  try:
    with open(pfn, 'r') as f:
      pfns = f.read().splitlines()
  except BaseException:
    pfns = [pfn]

  for pfn in pfns:
    result = dirac.getPhysicalFileAccessURL(pfn, seName, printOutput=True)
    if not result['OK']:
      print('ERROR: ', result['Message'])
      exitCode = 2

  DIRAC.exit(exitCode)


if __name__ == "__main__":
  main()
