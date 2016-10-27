# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

import os
import re
import codecs
import subprocess
import tarfile
import json

from packager import readMetadata, getDefaultFileName

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


def run(baseDir, type, version, keyFile, downloadsRepo):
    if type == 'gecko':
        import buildtools.packagerGecko as packager
    elif type == 'safari':
        import buildtools.packagerSafari as packager
    elif type == 'edge':
        import buildtools.packagerEdge as packager
    elif type == 'chrome':
        import buildtools.packagerChrome as packager

    # Replace version number in metadata file "manually", ConfigParser will mess
    # up the order of lines.
    metadata = readMetadata(baseDir, type)
    with open(metadata.option_source('general', 'version'), 'r+b') as file:
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
    if type == 'gecko':
        locales_base = baseDir
    else:
        # This is somewhat of a hack but reading out locale import config here would be too much
        locales_base = os.path.join(baseDir, 'adblockplus')

    locales = packagerGecko.readLocaleMetadata(locales_base, [packagerGecko.defaultLocale])
    extensionName = locales[packagerGecko.defaultLocale]['name']

    # Now commit the change and tag it
    subprocess.check_call(['hg', 'commit', '-R', baseDir, '-m', 'Releasing %s %s' % (extensionName, version)])
    tag_name = version
    if type in {'safari', 'edge'}:
        tag_name = '{}-{}'.format(tag_name, type)
    subprocess.check_call(['hg', 'tag', '-R', baseDir, '-f', tag_name])

    # Create a release build
    downloads = []
    if type == 'gecko':
        buildPath = os.path.join(downloadsRepo, getDefaultFileName(metadata, version, 'xpi'))
        packager.createBuild(baseDir, type=type, outFile=buildPath, releaseBuild=True)
        downloads.append(buildPath)
    elif type == 'chrome':
        # Create both signed and unsigned Chrome builds (the latter for Chrome Web Store).
        buildPath = os.path.join(downloadsRepo, getDefaultFileName(metadata, version, 'crx'))
        packager.createBuild(baseDir, type=type, outFile=buildPath, releaseBuild=True, keyFile=keyFile)
        downloads.append(buildPath)

        buildPathUnsigned = os.path.join(baseDir, getDefaultFileName(metadata, version, 'zip'))
        packager.createBuild(baseDir, type=type, outFile=buildPathUnsigned, releaseBuild=True, keyFile=None)
    elif type == 'safari':
        buildPath = os.path.join(downloadsRepo, getDefaultFileName(metadata, version, 'safariextz'))
        packager.createBuild(baseDir, type='safari', outFile=buildPath, releaseBuild=True, keyFile=keyFile)
        downloads.append(buildPath)
    elif type == 'edge':
        # We only offer the Edge extension for use through the Windows Store
        buildPath = os.path.join(downloadsRepo, getDefaultFileName(metadata, version, 'appx'))
        packager.createBuild(baseDir, type=type, outFile=buildPath, releaseBuild=True)
        downloads.append(buildPath)

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
