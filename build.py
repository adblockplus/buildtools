# coding: utf-8

# This Source Code is subject to the terms of the Mozilla Public License
# version 2.0 (the "License"). You can obtain a copy of the License at
# http://mozilla.org/MPL/2.0/.

import os, sys, re, subprocess, buildtools
from getopt import getopt, GetoptError

class Command(object):
  name = property(lambda self: self._name)
  shortDescription = property(lambda self: self._shortDescription,
      lambda self, value: self.__dict__.update({'_shortDescription': value}))
  description = property(lambda self: self._description,
      lambda self, value: self.__dict__.update({'_description': value}))
  params = property(lambda self: self._params,
      lambda self, value: self.__dict__.update({'_params': value}))
  supportedTypes = property(lambda self: self._supportedTypes,
      lambda self, value: self.__dict__.update({'_supportedTypes': value}))
  options = property(lambda self: self._options)

  def __init__(self, handler, name):
    self._handler = handler
    self._name = name
    self._shortDescription = ''
    self._description = ''
    self._params = ''
    self._supportedTypes = None
    self._options = []
    self.addOption('Show this message and exit', short='h', long='help')

  def __enter__(self):
    return self

  def __exit__(self, exc_type, exc_value, traceback):
    pass

  def __call__(self, baseDir, scriptName, opts, args, type):
    return self._handler(baseDir, scriptName, opts, args, type)

  def isSupported(self, type):
    return self._supportedTypes == None or type in self._supportedTypes

  def addOption(self, description, short=None, long=None, value=None):
    self._options.append((description, short, long, value))

  def parseArgs(self, args):
    shortOptions = map(lambda o: o[1]+':' if o[3] != None else o[1], filter(lambda o: o[1] != None, self._options))
    longOptions = map(lambda o: o[2]+'=' if o[3] != None else o[2], filter(lambda o: o[2] != None, self._options))
    return getopt(args, ''.join(shortOptions), longOptions)


commandsList = []
commands = {}
def addCommand(handler, name):
  if isinstance(name, basestring):
    aliases = ()
  else:
    name, aliases = (name[0], name[1:])

  global commandsList, commands
  command = Command(handler, name)
  commandsList.append(command)
  commands[name] = command
  for alias in aliases:
    commands[alias] = command
  return command

def splitByLength(string, maxLen):
  parts = []
  currentPart = ''
  for match in re.finditer(r'\s*(\S+)', string):
    if len(match.group(0)) + len(currentPart) < maxLen:
      currentPart += match.group(0)
    else:
      parts.append(currentPart)
      currentPart = match.group(1)
  if len(currentPart):
    parts.append(currentPart)
  return parts

def usage(scriptName, type, commandName=None):
  if commandName == None:
    global commandsList
    descriptions = []
    for command in commandsList:
      if not command.isSupported(type):
        continue
      commandText = ('%s %s' % (command.name, command.params)).ljust(39)
      descriptionParts = splitByLength(command.shortDescription, 29)
      descriptions.append('  %s %s %s' % (scriptName, commandText, descriptionParts[0]))
      for part in descriptionParts[1:]:
        descriptions.append('  %s %s %s' % (' ' * len(scriptName), ' ' * len(commandText), part))
    print '''Usage:

%(descriptions)s

For details on a command run:

  %(scriptName)s <command> --help
''' % {
    'scriptName': scriptName,
    'descriptions': '\n'.join(descriptions)
  }
  else:
    global commands
    command = commands[commandName]
    description = '\n'.join(map(lambda s: '\n'.join(splitByLength(s, 80)), command.description.split('\n')))
    options = []
    for descr, short, long, value in command.options:
      if short == None:
        shortText = ''
      elif value == None:
        shortText = '-%s' % short
      else:
        shortText = '-%s %s' % (short, value)
      if long == None:
        longText = ''
      elif value == None:
        longText = '--%s' % long
      else:
        longText = '--%s=%s' % (long, value)
      descrParts = splitByLength(descr, 46)
      options.append('  %s %s %s' % (shortText.ljust(11), longText.ljust(19), descrParts[0]))
      for part in descrParts[1:]:
        options.append('  %s %s %s' % (' ' * 11, ' ' * 19, part))
    print '''%(scriptName)s %(name)s %(params)s

%(description)s

Options:
%(options)s
''' % {
      'scriptName': scriptName,
      'name': command.name,
      'params': command.params,
      'description': description,
      'options': '\n'.join(options)
    }


def runBuild(baseDir, scriptName, opts, args, type):
  locales = None
  buildNum = None
  multicompartment = False
  releaseBuild = False
  keyFile = None
  limitMetadata = False
  for option, value in opts:
    if option in ('-l', '--locales'):
      locales = value.split(',')
    elif option in ('-b', '--build'):
      buildNum = int(value)
    elif option in ('-k', '--key'):
      keyFile = value
    elif option in ('-m', '--multi-compartment'):
      multicompartment = True
    elif option in ('-r', '--release'):
      releaseBuild = True
    elif option == '--babelzilla':
      locales = 'all'
      limitMetadata = True
  outFile = args[0] if len(args) > 0 else None

  if type == 'gecko':
    import buildtools.packager as packager
    packager.createBuild(baseDir, outFile=outFile, locales=locales, buildNum=buildNum,
                         releaseBuild=releaseBuild, keyFile=keyFile,
                         limitMetadata=limitMetadata, multicompartment=multicompartment)
  elif type == 'kmeleon':
    import buildtools.packagerKMeleon as packagerKMeleon
    packagerKMeleon.createBuild(baseDir, outFile=outFile, locales=locales,
                                buildNum=buildNum, releaseBuild=releaseBuild)

def runAutoInstall(baseDir, scriptName, opts, args, type):
  if len(args) == 0:
    print 'Port of the Extension Auto-Installer needs to be specified'
    usage(scriptName, type, 'autoinstall')
    return

  multicompartment = False
  for option, value in opts:
    if option in ('-m', '--multi-compartment'):
      multicompartment = True

  if ':' in args[0]:
    host, port = args[0].rsplit(':', 1)
  else:
    host, port = ('localhost', args[0])

  import buildtools.packager as packager
  packager.autoInstall(baseDir, host, port, multicompartment=multicompartment)


def showDescriptions(baseDir, scriptName, opts, args, type):
  locales = None
  for option, value in opts:
    if option in ('-l', '--locales'):
      locales = value.split(',')

  import buildtools.packager as packager
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


def generateDocs(baseDir, scriptName, opts, args, type):
  if len(args) == 0:
    print 'No target directory specified for the documentation'
    usage(scriptName, type, 'docs')
    return
  targetDir = args[0]

  toolkit = None
  for option, value in opts:
    if option in ('-t', '--toolkit'):
      toolkit = value

  if toolkit == None:
    toolkit = os.path.join(baseDir, 'jsdoc-toolkit')
    if not os.path.exists(toolkit):
      subprocess.Popen(['hg', 'clone', 'https://hg.adblockplus.org/jsdoc-toolkit/', toolkit]).communicate()

  command = [sys.executable,
             os.path.join(toolkit, 'jsrun.py'),
             '-t=' + os.path.join(toolkit, 'templates', 'jsdoc'),
             '-d=' + targetDir,
             '-a',
             '-p',
             '-x=js,jsm',
             os.path.join(baseDir, 'modules'),
             os.path.join(baseDir, 'components')]
  subprocess.Popen(command).communicate()


def runReleaseAutomation(baseDir, scriptName, opts, args, type):
  buildtoolsRepo = buildtools.__path__[0]
  keyFile = None
  downloadsRepo = os.path.join(baseDir, '..', 'downloads')
  for option, value in opts:
    if option in ('-k', '--key'):
      keyFile = value
    elif option in ('-d', '--downloads'):
      downloadsRepo = value

  if type == 'gecko':
    if len(args) == 0:
      print 'No version number specified for the release'
      usage(scriptName, type, 'release')
      return
    version = args[0]
    if re.search(r'[^\w\.]', version):
      print 'Wrong version number format'
      usage(scriptName, type, 'release')
      return

    if keyFile == None:
      print 'Warning: no key file specified, creating an unsigned release build\n'

    import buildtools.releaseAutomation as releaseAutomation
    releaseAutomation.run(baseDir, version, keyFile, downloadsRepo, buildtoolsRepo)
  else:
    import buildtools.releaseAutomationKMeleon as releaseAutomationKMeleon
    releaseAutomationKMeleon.run(baseDir, downloadsRepo, buildtoolsRepo)

with addCommand(lambda baseDir, scriptName, opts, args, type: usage(scriptName, type), ('help', '-h', '--help')) as command:
  command.shortDescription = 'Show this message'

with addCommand(runBuild, 'build') as command:
  command.shortDescription = 'Create a build'
  command.description = 'Creates an extension build with given file name. If output_file is missing a default name will be chosen.'
  command.params = '[options] [output_file]'
  command.addOption('Only include the given locales (if omitted: all locales not marked as incomplete)', short='l', long='locales', value='l1,l2,l3')
  command.addOption('Use given build number (if omitted the build number will be retrieved from Mercurial)', short='b', long='build', value='num')
  command.addOption('File containing private key and certificates required to sign the package', short='k', long='key', value='file')
  command.addOption('Create a build for leak testing', short='m', long='multi-compartment')
  command.addOption('Create a release build', short='r', long='release')
  command.addOption('Create a build for Babelzilla', long='babelzilla')
  command.supportedTypes = ('gecko', 'kmeleon')

with addCommand(runAutoInstall, 'autoinstall') as command:
  command.shortDescription = 'Install extension automatically'
  command.description = 'Will automatically install the extension in a browser running Extension Auto-Installer. If host parameter is omitted assumes that the browser runs on localhost.'
  command.params = '[<host>:]<port>'
  command.addOption('Create a build for leak testing', short='m', long='multi-compartment')
  command.supportedTypes = ('gecko')

with addCommand(showDescriptions, 'showdesc') as command:
  command.shortDescription = 'Print description strings for all locales'
  command.description = 'Display description strings for all locales as specified in the corresponding meta.properties files.'
  command.addOption('Only include the given locales', short='l', long='locales', value='l1,l2,l3')
  command.params = '[options]'
  command.supportedTypes = ('gecko')

with addCommand(generateDocs, 'docs') as command:
  command.shortDescription = 'Generate documentation'
  command.description = 'Generate documentation files and write them into the specified directory.'
  command.addOption('JsDoc Toolkit location', short='t', long='toolkit', value='dir')
  command.params = '[options] <directory>'
  command.supportedTypes = ('gecko')

with addCommand(runReleaseAutomation, 'release') as command:
  command.shortDescription = 'Run release automation'
  command.description = 'Note: If you are not the project owner then you '\
    'probably don\'t want to run this!\n\n'\
    'Runs release automation: creates downloads for the new version, tags '\
    'source code repository as well as downloads and buildtools repository.'
  command.addOption('File containing private key and certificates required to sign the release', short='k', long='key', value='file')
  command.addOption('Directory containing downloads repository (if omitted ../downloads is assumed)', short='d', long='downloads', value='dir')
  command.params = '[options] <version>'
  command.supportedTypes = ('gecko', 'kmeleon')

def processArgs(baseDir, args, type='gecko'):
  global commands

  scriptName = os.path.basename(args[0])
  args = args[1:]
  if len(args) == 0:
    args = ['build']
    print '''
No command given, assuming "build". For a list of commands run:

  %s help
''' % scriptName

  command = args[0]
  if command in commands:
    if commands[command].isSupported(type):
      try:
        opts, args = commands[command].parseArgs(args[1:])
      except GetoptError, e:
        print str(e)
        usage(scriptName, type, command)
        sys.exit(2)
      for option, value in opts:
        if option in ('-h', '--help'):
          usage(scriptName, type, command)
          sys.exit()
      commands[command](baseDir, scriptName, opts, args, type)
    else:
      print 'Command %s is not supported for this application type' % command
      usage(scriptName, type)
  else:
    print 'Command %s is unrecognized' % command
    usage(scriptName, type)
