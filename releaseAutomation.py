# coding: utf-8

# This file is part of the Adblock Plus build tools,
# Copyright (C) 2006-2013 Eyeo GmbH
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

import os, re, codecs, subprocess, tarfile, json
from StringIO import StringIO

def run(baseDir, type, version, keyFile, downloadsRepo):
  if type == "gecko":
    import buildtools.packagerGecko as packager
  elif type == "chrome":
    import buildtools.packagerChrome as packager

  # Replace version number in metadata file "manually", ConfigParser will mess
  # up the order of lines.
  handle = open(packager.getMetadataPath(baseDir, type), 'rb')
  rawMetadata = handle.read()
  handle.close()
  versionRegExp = re.compile(r'^(\s*version\s*=\s*).*', re.I | re.M)
  rawMetadata = re.sub(versionRegExp, r'\g<1>%s' % version, rawMetadata)
  handle = open(packager.getMetadataPath(baseDir, type), 'wb')
  handle.write(rawMetadata)
  handle.close()

  # Read extension name from locale data
  import buildtools.packagerGecko as packagerGecko
  if type == "gecko":
    locales_base = baseDir
  else:
    # This is somewhat of a hack but reading out locale import config here would be too much
    locales_base = os.path.join(baseDir, "adblockplus")

  locales = packagerGecko.readLocaleMetadata(locales_base, [packagerGecko.defaultLocale])
  extensionName = locales[packagerGecko.defaultLocale]['name']

  # Now commit the change and tag it
  subprocess.check_call(['hg', 'commit', '-R', baseDir, '-m', 'Releasing %s %s' % (extensionName, version)])
  subprocess.check_call(['hg', 'tag', '-R', baseDir, '-f', version])

  # Create a release build
  downloads = []
  if type == "gecko":
    metadata = packager.readMetadata(baseDir, type)
    buildPath = os.path.join(downloadsRepo, packager.getDefaultFileName(baseDir, metadata, version, 'xpi'))
    packager.createBuild(baseDir, type=type, outFile=buildPath, releaseBuild=True, keyFile=keyFile)
    downloads.append(buildPath)
  elif type == "chrome":
    # We actually have to create three different builds for Chrome: signed a unsigned Chrome builds
    # (the latter for Chrome Web Store) and a signed Opera build.
    metadata = packager.readMetadata(baseDir, type)
    buildPath = os.path.join(downloadsRepo, packager.getDefaultFileName(baseDir, metadata, version, 'crx'))
    packager.createBuild(baseDir, type=type, outFile=buildPath, releaseBuild=True, keyFile=keyFile)
    downloads.append(buildPath)

    buildPathUnsigned = os.path.join(baseDir, packager.getDefaultFileName(baseDir, metadata, version, 'zip'))
    packager.createBuild(baseDir, type=type, outFile=buildPathUnsigned, releaseBuild=True, keyFile=None)

    metadataOpera = packager.readMetadata(baseDir, "opera")
    buildPathOpera = os.path.join(downloadsRepo, packager.getDefaultFileName(baseDir, metadataOpera, version, 'crx'))
    packager.createBuild(baseDir, type="opera", outFile=buildPathOpera, releaseBuild=True, keyFile=keyFile)
    downloads.append(buildPathOpera)

  # Create source archive
  archivePath = os.path.splitext(buildPath)[0] + '-source.tgz'

  archiveHandle = open(archivePath, 'wb')
  archive = tarfile.open(fileobj=archiveHandle, name=os.path.basename(archivePath), mode='w:gz')
  data = subprocess.check_output(['hg', 'archive', '-R', baseDir, '-t', 'tar', '-S', '-'])
  repoArchive = tarfile.open(fileobj=StringIO(data), mode='r:')
  for fileInfo in repoArchive:
    if os.path.basename(fileInfo.name) in ('.hgtags', '.hgignore'):
      continue
    fileData = repoArchive.extractfile(fileInfo)
    fileInfo.name = re.sub(r'^[^/]+/', '', fileInfo.name)
    archive.addfile(fileInfo, fileData)
  repoArchive.close()
  archive.close()
  archiveHandle.close()
  downloads.append(archivePath)

  # Now add the downloads and commit
  subprocess.check_call(['hg', 'add', '-R', downloadsRepo] + downloads)
  subprocess.check_call(['hg', 'commit', '-R', downloadsRepo, '-m', 'Releasing %s %s' % (extensionName, version)])

  # Push all changes
  subprocess.check_call(['hg', 'push', '-R', baseDir])
  subprocess.check_call(['hg', 'push', '-R', downloadsRepo])
