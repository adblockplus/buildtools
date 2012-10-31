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

import os, re, subprocess, tarfile
from StringIO import StringIO
import buildtools.packagerGecko as packagerBase
import buildtools.packagerKMeleon as packagerKMeleon

def run(baseDir, downloadsRepo, buildtoolsRepo):
  baseExtDir = packagerKMeleon.getBaseExtensionDir(baseDir)

  # Read extension name, version and branch name
  locales = packagerBase.readLocaleMetadata(baseExtDir, [packagerBase.defaultLocale])
  extensionName = locales[packagerBase.defaultLocale]['name'] + ' for K-Meleon'

  metadata = packagerBase.readMetadata(baseExtDir)
  metadata.read(packagerBase.getMetadataPath(baseDir))
  branchName = metadata.get('general', 'branchname')
  version = metadata.get('general', 'version')

  # Tag our source repository
  subprocess.Popen(['hg', 'tag', '-R', baseDir, '-f', version]).communicate()

  # Create a release build
  buildPath = os.path.join(downloadsRepo, packagerBase.getDefaultFileName(baseDir, metadata, version, 'zip'))
  packagerKMeleon.createBuild(baseDir, outFile=buildPath, releaseBuild=True)

  # Create source archive
  archivePath = os.path.splitext(buildPath)[0] + '-source.tgz'

  archiveHandle = open(archivePath, 'wb')
  archive = tarfile.open(fileobj=archiveHandle, name=os.path.basename(archivePath), mode='w:gz')
  (data, dummy) = subprocess.Popen(['hg', 'archive', '-R', baseDir, '-t', 'tar', '-X', os.path.join(baseDir, '.hgtags'), '-'], stdout=subprocess.PIPE).communicate()
  repoArchive = tarfile.open(fileobj=StringIO(data), mode='r:')
  for fileInfo in repoArchive:
    fileData = repoArchive.extractfile(fileInfo)
    fileInfo.name = re.sub(r'^[^/]+/', '', fileInfo.name)
    archive.addfile(fileInfo, fileData)
  repoArchive.close()
  (data, dummy) = subprocess.Popen(['hg', 'archive', '-R', buildtoolsRepo, '-t', 'tar', '-X', os.path.join(buildtoolsRepo, '.hgtags'), '-'], stdout=subprocess.PIPE).communicate()
  repoArchive = tarfile.open(fileobj=StringIO(data), mode='r:')
  for fileInfo in repoArchive:
    fileData = repoArchive.extractfile(fileInfo)
    fileInfo.name = re.sub(r'^[^/]+/', 'buildtools/', fileInfo.name)
    archive.addfile(fileInfo, fileData)
  (data, dummy) = subprocess.Popen(['hg', 'archive', '-R', baseExtDir, '-t', 'tar', '-X', os.path.join(baseExtDir, '.hgtags'), '-'], stdout=subprocess.PIPE).communicate()
  repoArchive = tarfile.open(fileobj=StringIO(data), mode='r:')
  for fileInfo in repoArchive:
    fileData = repoArchive.extractfile(fileInfo)
    fileInfo.name = re.sub(r'^[^/]+/', '%s/' % os.path.basename(baseExtDir), fileInfo.name)
    archive.addfile(fileInfo, fileData)
  repoArchive.close()
  archive.close()
  archiveHandle.close()

  # Now add the downloads, commit and tag the downloads repo
  tagName = '%s_%s_RELEASE' % (branchName, version.replace('.', '_'))
  subprocess.Popen(['hg', 'add', '-R', downloadsRepo, buildPath, archivePath]).communicate()
  subprocess.Popen(['hg', 'commit', '-R', downloadsRepo, '-m', 'Releasing %s %s' % (extensionName, version)]).communicate()
  subprocess.Popen(['hg', 'tag', '-R', downloadsRepo, '-f', tagName]).communicate()

  # Tag buildtools repository as well
  subprocess.Popen(['hg', 'tag', '-R', buildtoolsRepo, '-f', tagName]).communicate()

  # Push all changes
  subprocess.Popen(['hg', 'push', '-R', baseDir]).communicate()
  subprocess.Popen(['hg', 'push', '-R', downloadsRepo]).communicate()
  subprocess.Popen(['hg', 'push', '-R', buildtoolsRepo]).communicate()
