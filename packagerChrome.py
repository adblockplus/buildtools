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

import sys, os, subprocess, re, json, codecs, struct, jinja2, buildtools
from ConfigParser import SafeConfigParser
from StringIO import StringIO
from zipfile import ZipFile, ZIP_DEFLATED

defaultLocale = 'en_US'

def getDefaultFileName(baseDir, metadata, ext):
  return os.path.join(baseDir, '%s-%s.%s' % (metadata.get('general', 'basename'), metadata.get('general', 'version'), ext))

def getMetadataPath(baseDir):
  return os.path.join(baseDir, 'metadata')

def getBuildNum(baseDir):
  try:
    (result, dummy) = subprocess.Popen(['hg', 'id', '-n'], stdout=subprocess.PIPE).communicate()
    return re.sub(r'\D', '', result)
  except Exception:
    return '0'

def getIgnoredFiles(params):
  return ['store.description']

def readMetadata(baseDir):
  metadata = SafeConfigParser()
  metadata.optionxform = str
  file = codecs.open(getMetadataPath(baseDir), 'rb', encoding='utf-8')
  metadata.readfp(file)
  file.close()
  return metadata

def getPackageFiles(params):
  baseDir = params['baseDir']
  for file in ('_locales', 'icons', 'jquery-ui', 'lib', 'skin', 'ui'):
    yield os.path.join(baseDir, file)
  if params['devenv']:
    yield os.path.join(baseDir, 'qunit')
  for file in os.listdir(baseDir):
    if file.endswith('.js') or file.endswith('.html') or file.endswith('.xml'):
      yield os.path.join(baseDir, file)

def createManifest(params):
  env = jinja2.Environment(loader=jinja2.FileSystemLoader(buildtools.__path__[0]))
  env.filters.update({'json': json.dumps})
  template = env.get_template('manifest.json.tmpl')
  templateData = dict(params)

  baseDir = templateData['baseDir']
  metadata = templateData['metadata']

  if metadata.has_option('general', 'pageAction'):
    icon, popup = re.split(r'\s+', metadata.get('general', 'pageAction'), 1)
    templateData['pageAction'] = {'icon': icon, 'popup': popup}

  if metadata.has_option('general', 'icons'):
    icons = {}
    iconsDir = baseDir
    for dir in metadata.get('general', 'icons').split('/')[0:-1]:
      iconsDir = os.path.join(iconsDir, dir)

    prefix, suffix = metadata.get('general', 'icons').split('/')[-1].split('?', 1)
    for file in os.listdir(iconsDir):
      path = os.path.join(iconsDir, file)
      if os.path.isfile(path) and file.startswith(prefix) and file.endswith(suffix):
        size = file[len(prefix):-len(suffix)]
        if not re.search(r'\D', size):
          icons[size] = os.path.relpath(path, baseDir).replace('\\', '/')

    templateData['icons'] = icons

  if metadata.has_option('general', 'permissions'):
    templateData['permissions'] = re.split(r'\s+', metadata.get('general', 'permissions'))
    if params['experimentalAPI']:
      templateData['permissions'].append('experimental')

  if metadata.has_option('general', 'backgroundScripts'):
    templateData['backgroundScripts'] = re.split(r'\s+', metadata.get('general', 'backgroundScripts'))

  if metadata.has_option('general', 'webAccessible'):
    templateData['webAccessible'] = re.split(r'\s+', metadata.get('general', 'webAccessible'))

  if metadata.has_section('contentScripts'):
    contentScripts = []
    for run_at, scripts in metadata.items('contentScripts'):
      contentScripts.append({
        'matches': ['http://*/*', 'https://*/*'],
        'js': re.split(r'\s+', scripts),
        'run_at': run_at,
        'all_frames': True,
      })
    templateData['contentScripts'] = contentScripts

  manifest = template.render(templateData)

  # Normalize JSON structure
  licenseComment = re.compile(r'/\*.*?\*/', re.S)
  data = json.loads(re.sub(licenseComment, '', manifest, 1))
  if '_dummy' in data:
    del data['_dummy']
  manifest = json.dumps(data, sort_keys=True, indent=2)

  return manifest.encode('utf-8')

def readFile(params, files, path):
  ignoredFiles = getIgnoredFiles(params)
  if os.path.isdir(path):
    for file in os.listdir(path):
      if file in ignoredFiles:
        continue
      readFile(params, files, os.path.join(path, file))
  else:
    file = open(path, 'rb')
    data = file.read()
    file.close()

    name = os.path.relpath(path, params['baseDir']).replace('\\', '/')
    files[name] = data

def convertJS(params, files):
  baseDir = params['baseDir']
  hydraDir = os.path.join(baseDir, 'jshydra')
  sys.path.append(hydraDir)
  try:
    if 'abp_rewrite' in sys.modules:
      import abp_rewrite
      reload(abp_rewrite.utils)
      reload(abp_rewrite)
    else:
      import abp_rewrite

    for file, sources in params['metadata'].items('convert_js'):
      dirsep = file.find('/')
      if dirsep >= 0:
        # Not a top-level file, make sure it is inside an included director
        dirname = file[0:dirsep]
        if os.path.join(baseDir, dirname) not in getPackageFiles(params):
          continue

      sourceFiles = re.split(r'\s+', sources)
      args = []
      try:
        argsStart = sourceFiles.index('--arg')
        args = sourceFiles[argsStart + 1:]
        sourceFiles = sourceFiles[0:argsStart]
      except ValueError:
        pass

      sourceFiles = map(lambda f: os.path.abspath(os.path.join(baseDir, f)), sourceFiles)
      files[file] = abp_rewrite.doRewrite(sourceFiles, args)
  finally:
    sys.path.remove(hydraDir)

def packFiles(files):
  buffer = StringIO()
  zip = ZipFile(buffer, 'w', ZIP_DEFLATED)
  for file, data in files.iteritems():
    zip.writestr(file, data)
  zip.close()
  return buffer.getvalue()

def signBinary(zipdata, keyFile):
  import M2Crypto
  if not os.path.exists(keyFile):
    M2Crypto.RSA.gen_key(1024, 65537, callback=lambda x: None).save_key(keyFile, cipher=None)
  key = M2Crypto.EVP.load_key(keyFile)
  key.sign_init()
  key.sign_update(zipdata)
  return key.final()

def getPublicKey(keyFile):
  import M2Crypto
  return M2Crypto.EVP.load_key(keyFile).as_der()

def writePackage(outputFile, pubkey, signature, zipdata):
  if isinstance(outputFile, basestring):
    file = open(outputFile, 'wb')
  else:
    file = outputFile
  if pubkey != None and signature != None:
    file.write(struct.pack('<4sIII', 'Cr24', 2, len(pubkey), len(signature)))
    file.write(pubkey)
    file.write(signature)
  file.write(zipdata)

def createBuild(baseDir, outFile=None, buildNum=None, releaseBuild=False, keyFile=None, experimentalAPI=False, devenv=False):
  metadata = readMetadata(baseDir)
  if outFile == None:
    outFile = getDefaultFileName(baseDir, metadata, 'crx' if keyFile else 'zip')

  version = metadata.get('general', 'version')
  if not releaseBuild:
    if buildNum == None:
      buildNum = getBuildNum(baseDir)
    if len(buildNum) > 0:
      while version.count('.') < 2:
        version += '.0'
      version += '.' + buildNum

  params = {
    'baseDir': baseDir,
    'releaseBuild': releaseBuild,
    'version': version,
    'experimentalAPI': experimentalAPI,
    'devenv': devenv,
    'metadata': metadata,
  }

  files = {}
  files['manifest.json'] = createManifest(params)
  for path in getPackageFiles(params):
    if os.path.exists(path):
      readFile(params, files, path)

  if metadata.has_section('convert_js') and os.path.isdir(os.path.join(baseDir, 'jshydra')):
    convertJS(params, files)

  zipdata = packFiles(files)
  signature = None
  pubkey = None
  if keyFile != None:
    signature = signBinary(zipdata, keyFile)
    pubkey = getPublicKey(keyFile)
  writePackage(outFile, pubkey, signature, zipdata)

def createDevEnv(baseDir):
  fileBuffer = StringIO()
  createBuild(baseDir, outFile=fileBuffer, devenv=True, releaseBuild=True)
  zip = ZipFile(StringIO(fileBuffer.getvalue()), 'r')
  zip.extractall(os.path.join(baseDir, 'devenv'))
  zip.close()
