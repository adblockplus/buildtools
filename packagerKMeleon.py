# coding: utf-8

# This file is part of the Adblock Plus build tools,
# Copyright (C) 2006-2012 Eyeo GmbH
#
# Adblock Plus is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 3 as
# published by the Free Software Foundation.
#
# Adblock Plus is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with Adblock Plus.  If not, see <http://www.gnu.org/licenses/>.

import os, subprocess, re, tempfile, shutil, json
import buildtools.packagerGecko as packagerBase

libs = (
  'libcmt.lib', 'kernel32.lib', 'user32.lib', 'gdi32.lib', 'comctl32.lib',
  'nspr4.lib', 'plds4.lib', 'plc4.lib', 'xpcom.lib', 'xpcomglue_s.lib',
  'embed_base_s.lib', 'unicharutil_external_s.lib', 'js3250.lib'
)
compileflags = ('-c', '-O1', '-W3', '-MT', '-DXP_WIN', '-Zc:wchar_t-')
linkflags = ('-DLL', '-NODEFAULTLIB', '-NOLOGO')
versionflag = '-DABP_VERSION="%s"'

def getKMeleonSourceDir(baseDir):
  return os.path.join(baseDir, 'kmeleon_src')

def getGeckoDir(baseDir):
  return os.path.join(getKMeleonSourceDir(baseDir), 'mozilla', 'mozilla', 'dist')

def getBaseExtensionDir(baseDir):
  return os.path.join(baseDir, 'adblockplus')

def getIncludeDirs(baseDir):
  yield os.path.join(getKMeleonSourceDir(baseDir), 'src')
  geckoIncludeDir = os.path.join(getGeckoDir(baseDir), 'include')
  for dir in ('caps', 'content', 'dom', 'gfx', 'imglib2', 'js', 'layout',
              'necko', 'nspr', 'pref', 'string', 'webbrwsr', 'widget', 'xpcom',
              'xpconnect'):
    yield os.path.join(geckoIncludeDir, dir)

def getLibDirs(baseDir):
  yield os.path.join(getGeckoDir(baseDir), 'lib')

def getFileList(baseDir, ext):
  for file in os.listdir(baseDir):
    path = os.path.join(baseDir, file)
    if os.path.isfile(path) and file.endswith(ext):
      yield path

def getSourceFiles(baseDir):
  return getFileList(baseDir, '.cpp')

def getXULFiles(baseDir):
  return getFileList(baseDir, '.xul')

def getMacroFiles(baseDir):
  return getFileList(baseDir, '.kmm')

def getInterfaceFiles(baseDir):
  return getFileList(baseDir, '.xpt')

def getModuleFiles(baseDir):
  return getFileList(baseDir, '.jsm')

def getPrefsFiles(baseDir):
  return getFileList(baseDir, '.js')

def buildDLL(baseDir, fileName, version):
  tempDir = tempfile.mkdtemp()
  try:
    objFiles = []
    for sourceFile in getSourceFiles(baseDir):
      objFile = os.path.join(tempDir, os.path.splitext(os.path.basename(sourceFile))[0] + '.obj')
      objFiles.append(objFile)
      command = ['cl']
      command.extend(compileflags)
      command.append(versionflag % version)
      command.extend(map(lambda d: '-I%s' % d, getIncludeDirs(baseDir)))
      command.append(sourceFile)
      command.append('-Fo%s' % objFile)
      subprocess.Popen(command).communicate()

    outFile = os.path.join(tempDir, fileName)
    command = ['link']
    command.extend(objFiles)
    command.extend(libs)
    command.extend(linkflags)
    command.extend(map(lambda d: '-LIBPATH:%s' % d, getLibDirs(baseDir)))
    command.append('-OUT:%s' % outFile)
    subprocess.Popen(command).communicate()

    handle = open(outFile, 'rb')
    result = handle.read()
    handle.close()
    return result
  finally:
    shutil.rmtree(tempDir, ignore_errors=True)

def createManifest(baseExtDir, params):
  localeMetadata = packagerBase.readLocaleMetadata(baseExtDir, params['locales'])

  manifest = {}
  metadata = params['metadata']
  manifest['id'] = metadata.get('general', 'id')
  manifest['version'] = metadata.get('general', 'version')
  manifest['version'] = params['version']
  manifest['name'] = localeMetadata[packagerBase.defaultLocale]['name']
  manifest['description'] = localeMetadata[packagerBase.defaultLocale]['description']
  manifest['creator'] = metadata.get('general', 'author')
  manifest['homepage'] = metadata.get('homepage', 'default')
  if metadata.has_section('contributors'):
    manifest['contributors'] = map(lambda item: item[1], metadata.items('contributors'))
    manifest['contributors'].sort()
  else:
    manifest['contributors'] = []
  manifest['translators'] = packagerBase.getTranslators(localeMetadata)
  return 'var EXPORTED_SYMBOLS = ["manifest"];\nvar manifest = ' + json.dumps(manifest)

def processChromeManifest(data, baseName):
  # Manifest location is different in K-Meleon, update paths
  data = re.sub(r'jar:chrome/', 'jar:', data)
  data = re.sub(r'(\s)modules/', r'\1../modules/%s/' % baseName, data)
  data = re.sub(r'(\s)defaults/', r'\1../defaults/', data)
  return data

def createBuild(baseDir, outFile=None, locales=None, buildNum=None, releaseBuild=False):
  if buildNum == None:
    buildNum = packagerBase.getBuildNum(baseDir)

  baseExtDir = getBaseExtensionDir(baseDir)
  if locales == None:
    locales = packagerBase.getLocales(baseExtDir)
  elif locales == 'all':
    locales = packagerBase.getLocales(baseExtDir, True)

  metadata = packagerBase.readMetadata(baseExtDir)
  version = metadata.get('general', 'version')
  if not releaseBuild:
    version += '.' + buildNum

  params = {
    'locales': locales,
    'releaseBuild': releaseBuild,
    'buildNum': buildNum,
    'version': version.encode('utf-8'),
    'metadata': metadata,
    'limitMetadata': False,
  }
  baseName = metadata.get('general', 'basename')

  chromeFiles = {}
  for xulFile in getXULFiles(baseDir):
    packagerBase.readFile(chromeFiles, params, xulFile, 'content/ui/%s' % os.path.basename(xulFile))

  files = {}
  files['modules/%s/Manifest.jsm' % baseName] = createManifest(baseExtDir, params)
  files['kplugins/%s.dll' % baseName] = buildDLL(baseDir, '%s.dll' % baseName, version)
  files['chrome/%s.jar' % baseName] = packagerBase.createChromeJar(baseExtDir, params, files=chromeFiles)

  packagerBase.readFile(files, params, os.path.join(baseExtDir, 'chrome.manifest'), 'chrome/%s.manifest' % baseName)
  files['chrome/%s.manifest' % baseName] = processChromeManifest(files['chrome/%s.manifest' % baseName], baseName)

  for macroFile in getMacroFiles(baseDir):
    packagerBase.readFile(files, params, macroFile, 'macros/%s' % os.path.basename(macroFile))
  for interfaceFile in getInterfaceFiles(baseDir):
    packagerBase.readFile(files, params, interfaceFile, 'components/%s' % os.path.basename(interfaceFile))
  for moduleFile in getModuleFiles(baseDir):
    packagerBase.readFile(files, params, moduleFile, 'modules/%s/%s' % (baseName, os.path.basename(moduleFile)))
  for prefsFile in getPrefsFiles(baseDir):
    packagerBase.readFile(files, params, prefsFile, 'defaults/pref/%s' % os.path.basename(prefsFile))

  packagerBase.readFile(files, params, os.path.join(baseExtDir, 'defaults'), 'defaults')
  packagerBase.readFile(files, params, os.path.join(baseExtDir, 'modules'), 'modules/%s' %baseName)

  # Correct files names (defaults/preferences/ => defaults/pref/)
  newFiles = {}
  for key, value in files.iteritems():
    if key.startswith('defaults/preferences/'):
      key = 'defaults/pref/' + key[len('defaults/preferences/'):]
    newFiles[key] = value
  files = newFiles

  # Allow local metadata to overrite settings from base extension
  metadata.read(packagerBase.getMetadataPath(baseDir))
  if outFile == None:
    outFile = packagerBase.getDefaultFileName(baseDir, metadata, version, 'zip')

  packagerBase.writeXPI(files, outFile)
