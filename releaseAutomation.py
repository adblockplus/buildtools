# coding: utf-8

# This Source Code is subject to the terms of the Mozilla Public License
# version 2.0 (the "License"). You can obtain a copy of the License at
# http://mozilla.org/MPL/2.0/.

import os, re, subprocess, tarfile
from StringIO import StringIO
import buildtools.packager as packager

def run(baseDir, version, keyFile, downloadsRepo, buildtoolsRepo):
  # Replace version number in metadata file "manually", ConfigParser will mess
  # up the order of lines.
  handle = open(packager.getMetadataPath(baseDir), 'rb')
  rawMetadata = handle.read()
  handle.close()
  versionRegExp = re.compile(r'^(\s*version\s*=\s*).*', re.I | re.M)
  rawMetadata = re.sub(versionRegExp, r'\g<1>%s' % version, rawMetadata)
  handle = open(packager.getMetadataPath(baseDir), 'wb')
  handle.write(rawMetadata)
  handle.close()

  # Read extension name and branch name
  locales = packager.readLocaleMetadata(baseDir, [packager.defaultLocale])
  extensionName = locales[packager.defaultLocale]['name']

  metadata = packager.readMetadata(baseDir)
  branchName = metadata.get('general', 'branchname')

  # Now commit the change and tag it
  subprocess.Popen(['hg', 'commit', '-R', baseDir, '-m', 'Releasing %s %s' % (extensionName, version)]).communicate()
  subprocess.Popen(['hg', 'tag', '-R', baseDir, '-f', version]).communicate()

  # Create a release build
  buildPath = os.path.join(downloadsRepo, packager.getDefaultFileName(baseDir, metadata, version))
  packager.createBuild(baseDir, outFile=buildPath, releaseBuild=True, keyFile=keyFile)

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
