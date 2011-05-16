# coding: utf-8

# The contents of this file are subject to the Mozilla Public License
# Version 1.1 (the "License"); you may not use this file except in
# compliance with the License. You may obtain a copy of the License at
# http://www.mozilla.org/MPL/

import os, sys
from getopt import getopt, GetoptError
import buildtools.packager as packager

def usage_build(scriptName):
  print '''%(name)s build [options] [output_file]

Creates an extension build with given file name. If output_file is missing a
default name will be chosen.

Options:
  -h          --help              Show this message and exit
  -l l1,l2,l3 --locales=l1,l2,l3  Only include the given locales (if omitted:
                                  all locales not marked as incomplete)
  -b num      --build=num         Use given build number (if omitted the build
                                  number will be retrieved from Mercurial)
  -k file     --key=file          File containing private key and certificates
                                  required to sign the package
  -r          --release           Create a release build
              --babelzilla        Create a build for Babelzilla
''' % {"name": scriptName}

def runBuild(baseDir, scriptName, args):
  try:
    opts, args = getopt(args, 'hl:b:k:r:', ['help', 'locales', 'build=', 'key=', 'release', 'babelzilla'])
  except GetoptError, e:
    print str(e)
    usage_build(scriptName)
    sys.exit(2)

  locales = None
  buildNum = None
  releaseBuild = False
  keyFile = None
  limitMetadata = False
  for option, value in opts:
    if option in ('-h', '--help'):
      usage_build(scriptName)
      return
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
  outFile = args[0] if len(args) > 0 else None

  packager.createBuild(baseDir, outFile=outFile, locales=locales, buildNum=buildNum,
                       releaseBuild=releaseBuild, keyFile=keyFile,
                       limitMetadata=limitMetadata)


def usage_testenv(scriptName):
  print '''%(name)s testenv [options] [profile_dir] ...

Sets up the extension in given profiles in such a way that most files are read
from the current directory. Changes in the files here will be available to these
profiles immediately after a restart without having to reinstall the extension.
If no directories are given the list of directories is read from a file.

Options
  -h          --help              Show this message and exit
  -d file     --dirs=file         File listing profile directories to set up if
                                  none are given on command line (default is
                                  .profileDirs)
''' % {"name": scriptName}

def setupTestEnvironment(baseDir, scriptName, args):
  try:
    opts, args = getopt(args, 'hd:', ['help', 'dirs='])
  except GetoptError, e:
    print str(e)
    usage_testenv(scriptName)
    sys.exit(2)

  dirsFile = '.profileDirs'
  for option, value in opts:
    if option in ('-h', '--help'):
      usage_testenv(scriptName)
      return
    elif option in ('-d', '--dirs'):
      dirsFile = value

  profileDirs = args
  if len(profileDirs) == 0:
    handle = open(dirsFile, 'rb')
    profileDirs = map(str.strip, handle.readlines())
    handle.close()
  packager.setupTestEnvironment(baseDir, profileDirs)


def usage_showdesc(scriptName):
  print '''%(name)s showdesc [options]

Display description strings for all locales as specified in the corresponding
meta.properties files.

Options
  -h          --help              Show this message and exit
  -l l1,l2,l3 --locales=l1,l2,l3  Only include the given locales
''' % {"name": scriptName}

def showDescriptions(baseDir, scriptName, args):
  try:
    opts, args = getopt(args, 'hl:', ['help', 'locales='])
  except GetoptError, e:
    print str(e)
    usage_showdesc(scriptName)
    sys.exit(2)

  locales = None
  for option, value in opts:
    if option in ('-h', '--help'):
      usage_showdesc(scriptName)
      return
    elif option in ('-l', '--locales'):
      locales = value.split(',')

  if locales == None:
    locales = packager.getLocales(baseDir)
  elif locales == 'all':
    locales = packager.getLocales(baseDir, True)

  data = packager.readLocaleMetadata(baseDir, locales)
  localeCodes = data.keys()
  localeCodes.sort()
  for localeCode in localeCodes:
    locale = data[localeCode]
    print ('''%s
%s
%s
%s
%s
''' % (localeCode,
       locale['name'] if 'name' in locale else 'None',
       locale['description'] if 'description' in locale else 'None',
       locale['description.short'] if 'description.short' in locale else 'None',
       locale['description.long'] if 'description.long' in locale else 'None',
      )).encode('utf-8')

def usage(scriptName):
  print '''Usage:

  %(name)s help                                   Show this message
  %(name)s build [options] [output_file]          Create a build
  %(name)s testenv [options] [profile_dir] ...    Set up test environment
  %(name)s showdesc [options]                     Print description strings for
                                                  all locales

For details on a command run:

  %(name)s <command> --help
''' % {"name": scriptName}

def processArgs(baseDir, args):
  scriptName = os.path.basename(args[0])
  args = args[1:]
  if len(args) == 0:
    args = ['build']
    print '''
No command given, assuming "build". For a list of commands run:

  %s help
''' % scriptName

  command = args[0]
  if command == 'help' or command == '--help' or command == '-h':
    usage(scriptName)
  elif command == 'build':
    runBuild(baseDir, scriptName, args[1:])
  elif command == 'testenv':
    setupTestEnvironment(baseDir, scriptName, args[1:])
  elif command == 'showdesc':
    showDescriptions(baseDir, scriptName, args[1:])
  else:
    print 'Command %s is unrecognized' % command
    usage(scriptName)
