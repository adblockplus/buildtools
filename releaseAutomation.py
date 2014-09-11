# coding: utf-8

# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

import os, re, codecs, subprocess, tarfile, json

def get_dependencies(prefix, repos):
  from ensure_dependencies import read_deps, safe_join
  repo = repos[prefix]
  deps = read_deps(repo)
  if deps:
    for subpath in deps:
      if subpath.startswith('_'):
        continue
      depprefix = prefix + subpath + '/'
      deppath = safe_join(repo, subpath)
      repos[depprefix] = deppath
      get_dependencies(depprefix, repos)

def create_sourcearchive(repo, output):
  with tarfile.open(output, mode='w:gz') as archive:
    repos = {'': repo}
    get_dependencies('', repos)
    for prefix, path in repos.iteritems():
      process = subprocess.Popen(['hg', 'archive', '-R', path, '-t', 'tar', '-S', '-'], stdout=subprocess.PIPE)
      try:
        with tarfile.open(fileobj=process.stdout, mode='r|') as repoarchive:
          for fileinfo in repoarchive:
            if os.path.basename(fileinfo.name) in ('.hgtags', '.hgignore'):
              continue
            filedata = repoarchive.extractfile(fileinfo)
            fileinfo.name = re.sub(r'^[^/]+/', prefix, fileinfo.name)
            archive.addfile(fileinfo, filedata)
      finally:
        process.stdout.close()
        process.wait()

def run(baseDir, type, version, keyFiles, downloadsRepo):
  if type == "gecko":
    import buildtools.packagerGecko as packager
  elif type == "chrome":
    import buildtools.packagerChrome as packager

  # Replace version number in metadata file "manually", ConfigParser will mess
  # up the order of lines.
  metadata = packager.readMetadata(baseDir, type)
  with open(metadata.option_source("general", "version"), 'r+b') as file:
    rawMetadata = file.read()
    rawMetadata = re.sub(
      r'^(\s*version\s*=\s*).*', r'\g<1>%s' % version,
      rawMetadata, flags=re.I | re.M
    )

    file.seek(0)
    file.write(rawMetadata)
    file.truncate()

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
    keyFile = keyFiles[0] if keyFiles else None
    metadata = packager.readMetadata(baseDir, type)
    buildPath = os.path.join(downloadsRepo, packager.getDefaultFileName(baseDir, metadata, version, 'xpi'))
    packager.createBuild(baseDir, type=type, outFile=buildPath, releaseBuild=True, keyFile=keyFile)
    downloads.append(buildPath)
  elif type == "chrome":
    # We actually have to create four different builds for Chrome: signed a unsigned Chrome builds
    # (the latter for Chrome Web Store), a signed Opera build and a signed Safari build.
    metadata = packager.readMetadata(baseDir, type)
    buildPath = os.path.join(downloadsRepo, packager.getDefaultFileName(baseDir, metadata, version, 'crx'))
    packager.createBuild(baseDir, type=type, outFile=buildPath, releaseBuild=True, keyFile=keyFiles[0])
    downloads.append(buildPath)

    buildPathUnsigned = os.path.join(baseDir, packager.getDefaultFileName(baseDir, metadata, version, 'zip'))
    packager.createBuild(baseDir, type=type, outFile=buildPathUnsigned, releaseBuild=True, keyFile=None)

    metadataOpera = packager.readMetadata(baseDir, "opera")
    buildPathOpera = os.path.join(downloadsRepo, packager.getDefaultFileName(baseDir, metadataOpera, version, 'crx'))
    packager.createBuild(baseDir, type="opera", outFile=buildPathOpera, releaseBuild=True, keyFile=keyFiles[0])
    downloads.append(buildPathOpera)

    import buildtools.packagerSafari as packagerSafari
    metadataSafari = packagerSafari.readMetadata(baseDir, "safari")
    buildPathSafari = os.path.join(downloadsRepo, packagerSafari.getDefaultFileName(baseDir, metadataSafari, version, 'safariextz'))
    packagerSafari.createBuild(baseDir, type="safari", outFile=buildPathSafari, releaseBuild=True, keyFile=keyFiles[1])
    downloads.append(buildPathSafari)

  # Create source archive
  archivePath = os.path.splitext(buildPath)[0] + '-source.tgz'
  create_sourcearchive(baseDir, archivePath)
  downloads.append(archivePath)

  # Now add the downloads and commit
  subprocess.check_call(['hg', 'add', '-R', downloadsRepo] + downloads)
  subprocess.check_call(['hg', 'commit', '-R', downloadsRepo, '-m', 'Releasing %s %s' % (extensionName, version)])

  # Push all changes
  subprocess.check_call(['hg', 'push', '-R', baseDir])
  subprocess.check_call(['hg', 'push', '-R', downloadsRepo])
