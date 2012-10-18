# coding: utf-8

# This Source Code is subject to the terms of the Mozilla Public License
# version 2.0 (the "License"). You can obtain a copy of the License at
# http://mozilla.org/MPL/2.0/.

import sys, os, subprocess, re, json, codecs, struct
from ConfigParser import SafeConfigParser
from StringIO import StringIO
from zipfile import ZipFile, ZIP_DEFLATED

def getDefaultFileName(baseDir, metadata, version, ext):
  return os.path.join(baseDir, '%s-%s.%s' % (metadata.get('general', 'baseName'), version, ext))

def getMetadataPath(baseDir):
  return os.path.join(baseDir, 'metadata')

def getBuildNum(baseDir):
  try:
    (result, dummy) = subprocess.Popen(['hg', 'id', '-n'], stdout=subprocess.PIPE).communicate()
    return re.sub(r'\D', '', result)
  except Exception:
    return '0'

def readMetadata(baseDir):
  metadata = SafeConfigParser()
  file = codecs.open(getMetadataPath(baseDir), 'rb', encoding='utf-8')
  metadata.readfp(file)
  file.close()
  return metadata

def readVersion(baseDir):
  file = open(os.path.join(baseDir, 'manifest.json'))
  data = json.load(file)
  file.close()
  return data['version']

def setUpdateURL(updateName, zip, dir, fileName, fileData):
  if fileName == 'manifest.json':
    data = json.loads(fileData)
    data['update_url'] = 'https://adblockplus.org/devbuilds/%s/updates.xml' % updateName
    return json.dumps(data, sort_keys=True, indent=2)
  return fileData

def setExperimentalSettings(zip, dir, fileName, fileData):
  if fileName == 'manifest.json':
    data = json.loads(fileData)
    data['permissions'] += ['experimental']
    data['name'] += ' experimental build'
    return json.dumps(data, sort_keys=True, indent=2)
  return fileData

def addBuildNumber(revision, zip, dir, fileName, fileData):
  if fileName == 'manifest.json':
    if len(revision) > 0:
      data = json.loads(fileData)
      while data['version'].count('.') < 2:
        data['version'] += '.0'
      data['version'] += '.' + revision
      return json.dumps(data, sort_keys=True, indent=2)
  return fileData

def mergeContentScripts(zip, dir, fileName, fileData):
  if fileName == 'manifest.json':
    data = json.loads(fileData)
    if 'content_scripts' in data:
      scriptIndex = 1
      for contentScript in data['content_scripts']:
        if 'js' in contentScript:
          scriptData = ''
          for scriptFile in contentScript['js']:
            parts = [dir] + scriptFile.split('/')
            scriptPath = os.path.join(*parts)
            handle = open(scriptPath, 'rb')
            scriptData += handle.read()
            handle.close()
          contentScript['js'] = ['contentScript' + str(scriptIndex) + '.js']
          zip.writestr('contentScript' + str(scriptIndex) + '.js', scriptData)
          scriptIndex += 1
    return json.dumps(data, sort_keys=True, indent=2)
  return fileData

def addToZip(zip, filters, dir, baseName):
  for file in os.listdir(dir):
    filelc = file.lower()
    if (file.startswith('.') or
        file == 'buildtools' or file == 'qunit' or file == 'metadata' or
        filelc.endswith('.py') or filelc.endswith('.pyc') or
        filelc.endswith('.crx') or filelc.endswith('.zip') or
        filelc.endswith('.sh') or filelc.endswith('.bat') or
        filelc.endswith('.txt')):
      # skip special files, scripts, existing archives
      continue
    if file.startswith('include.'):
      # skip includes, they will be added by other means
      continue

    filePath = os.path.join(dir, file)
    if os.path.isdir(filePath):
      addToZip(zip, filters, filePath, baseName + file + '/')
    else:
      handle = open(filePath, 'rb')
      fileData = handle.read()
      handle.close()

      for filter in filters:
        fileData = filter(zip, dir, baseName + file, fileData)
      zip.writestr(baseName + file, fileData)

def packDirectory(dir, filters):
  buffer = StringIO()
  zip = ZipFile(buffer, 'w', ZIP_DEFLATED)
  addToZip(zip, filters, dir, '')
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
  file = open(outputFile, 'wb')
  if pubkey != None and signature != None:
    file.write(struct.pack('<4sIII', 'Cr24', 2, len(pubkey), len(signature)))
    file.write(pubkey)
    file.write(signature)
  file.write(zipdata)
  file.close()

def createBuild(baseDir, outFile=None, buildNum=None, releaseBuild=False, keyFile=None, experimentalAPI=False):
  metadata = readMetadata(baseDir)
  version = readVersion(baseDir)
  if outFile == None:
    outFile = getDefaultFileName(baseDir, metadata, version, 'crx' if keyFile else 'zip')

  filters = []
  if not releaseBuild:
    if buildNum == None:
      buildNum = getBuildNum(baseDir)
    filters.append(lambda zip, dir, fileName, fileData: addBuildNumber(buildNum, zip, dir, fileName, fileData))

    baseName = metadata.get('general', 'baseName')
    updateName = baseName + '-experimental' if experimentalAPI else baseName
    filters.append(lambda zip, dir, fileName, fileData: setUpdateURL(updateName, zip, dir, fileName, fileData))
    if experimentalAPI:
      filters.append(setExperimentalSettings)
  filters.append(mergeContentScripts)

  zipdata = packDirectory(baseDir, filters)
  signature = None
  pubkey = None
  if keyFile != None:
    signature = signBinary(zipdata, keyFile)
    pubkey = getPublicKey(keyFile)
  writePackage(outFile, pubkey, signature, zipdata)
