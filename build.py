# coding: utf-8

# The contents of this file are subject to the Mozilla Public License
# Version 1.1 (the "License"); you may not use this file except in
# compliance with the License. You may obtain a copy of the License at
# http://www.mozilla.org/MPL/

import os, sys
from getopt import getopt, GetoptError
import buildtools.packager as packager

def usage():
  print '''Usage: %s [output_file]

Options:
  -h          --help              Print this message and exit
  -l l1,l2,l3 --locales=l1,l2,l3  Only include the given locales (if omitted:
                                  all locales not marked as incomplete)
  -b num      --build=num         Use given build number (if omitted the build
                                  number will be retrieved from Mercurial)
  -k file     --key=file          File containing private key and certificates
                                  required to sign the package
  -r          --release           Create a release build
              --babelzilla        Create a build for Babelzilla
''' % os.path.basename(sys.argv[0])

def processArgs(baseDir, args):
  try:
    opts, args = getopt(sys.argv[1:], 'hl:b:k:r', ['help', 'locales', 'build=', 'key=', 'release', 'babelzilla'])
  except GetoptError, e:
    print str(e)
    usage()
    sys.exit(2)

  locales = None
  buildNum = None
  releaseBuild = False
  keyFile = None
  limitMetadata = False
  for option, value in opts:
    if option in ('-h', '--help'):
      usage()
      sys.exit()
    elif option in ('-l', '--locales'):
      locales = value.split(',')
    elif option in ('-b', '--build'):
      buildNum = int(value)
    elif option in ('-k', '--key'):
      keyFile = value
    elif option in ('-r', '--release'):
      releaseBuild = True
    elif option == '--babelzilla':
      locales = 'all'
      limitMetadata = True

  outFile = None
  if len(args) >= 1:
    outFile = args[0]

  packager.createBuild(baseDir, outFile=outFile, locales=locales, buildNum=buildNum,
                       releaseBuild=releaseBuild, keyFile=keyFile,
                       limitMetadata=limitMetadata)
