# coding: utf-8

# This Source Code is subject to the terms of the Mozilla Public License
# version 2.0 (the "License"). You can obtain a copy of the License at
# http://mozilla.org/MPL/2.0/.

import os, subprocess, re, tempfile, shutil, json
import buildtools.packager as packager

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
  localeMetadata = packager.readLocaleMetadata(baseExtDir, params['locales'])

  manifest = {}
  metadata = params['metadata']
  manifest['id'] = metadata.get('general', 'id')
  manifest['version'] = metadata.get('general', 'version')
  manifest['version'] = params['version']
  manifest['name'] = localeMetadata[packager.defaultLocale]['name']
  manifest['description'] = localeMetadata[packager.defaultLocale]['description']
  manifest['creator'] = metadata.get('general', 'author')
  manifest['homepage'] = metadata.get('homepage', 'default')
  if metadata.has_section('contributors'):
    manifest['contributors'] = map(lambda item: item[1], metadata.items('contributors'))
    manifest['contributors'].sort()
  else:
    manifest['contributors'] = []
  manifest['translators'] = packager.getTranslators(localeMetadata)
  return 'var EXPORTED_SYMBOLS = ["manifest"];\nvar manifest = ' + json.dumps(manifest)

def processChromeManifest(data, baseName):
  # Manifest location is different in K-Meleon, update paths
  data = re.sub(r'jar:chrome/', 'jar:', data)
  data = re.sub(r'(\s)modules/', r'\1../modules/%s/' % baseName, data)
  data = re.sub(r'(\s)defaults/', r'\1../defaults/', data)
  return data

def createBuild(baseDir, outFile=None, locales=None, buildNum=None, releaseBuild=False):
  if buildNum == None:
    buildNum = packager.getBuildNum(baseDir)

  baseExtDir = getBaseExtensionDir(baseDir)
  if locales == None:
    locales = packager.getLocales(baseExtDir)
  elif locales == 'all':
    locales = packager.getLocales(baseExtDir, True)

  metadata = packager.readMetadata(baseExtDir)
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
  baseName = metadata.get('general', 'baseName')

  chromeFiles = {}
  for xulFile in getXULFiles(baseDir):
    packager.readFile(chromeFiles, params, xulFile, 'content/ui/%s' % os.path.basename(xulFile))

  files = {}
  files['modules/%s/Manifest.jsm' % baseName] = createManifest(baseExtDir, params)
  files['kplugins/%s.dll' % baseName] = buildDLL(baseDir, '%s.dll' % baseName, version)
  files['chrome/%s.jar' % baseName] = packager.createChromeJar(baseExtDir, params, files=chromeFiles)

  packager.readFile(files, params, os.path.join(baseExtDir, 'chrome.manifest'), 'chrome/%s.manifest' % baseName)
  files['chrome/%s.manifest' % baseName] = processChromeManifest(files['chrome/%s.manifest' % baseName], baseName)

  for macroFile in getMacroFiles(baseDir):
    packager.readFile(files, params, macroFile, 'macros/%s' % os.path.basename(macroFile))
  for interfaceFile in getInterfaceFiles(baseDir):
    packager.readFile(files, params, interfaceFile, 'components/%s' % os.path.basename(interfaceFile))
  for moduleFile in getModuleFiles(baseDir):
    packager.readFile(files, params, moduleFile, 'modules/%s/%s' % (baseName, os.path.basename(moduleFile)))
  for prefsFile in getPrefsFiles(baseDir):
    packager.readFile(files, params, prefsFile, 'defaults/pref/%s' % os.path.basename(prefsFile))

  packager.readFile(files, params, os.path.join(baseExtDir, 'defaults'), 'defaults')
  packager.readFile(files, params, os.path.join(baseExtDir, 'modules'), 'modules/%s' %baseName)

  # Correct files names (defaults/preferences/ => defaults/pref/)
  newFiles = {}
  for key, value in files.iteritems():
    if key.startswith('defaults/preferences/'):
      key = 'defaults/pref/' + key[len('defaults/preferences/'):]
    newFiles[key] = value
  files = newFiles

  # Allow local metadata to overrite settings from base extension
  metadata.read(packager.getMetadataPath(baseDir))
  if outFile == None:
    outFile = packager.getDefaultFileName(baseDir, metadata, version, 'zip')

  packager.writeXPI(files, outFile)
