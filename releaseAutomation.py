# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

from __future__ import print_function

import os
import operator
import re
import codecs
import logging
import subprocess
import sys
import tarfile
import json

from packager import readMetadata, getDefaultFileName, get_extension
from localeTools import read_locale_config

SOURCE_ARCHIVE = 'adblockplus-{}-source.tgz'


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


def repo_has_uncommitted():
    """Checks if the given repository is clean"""
    buff = subprocess.check_output(['hg', 'status'])

    if len(buff):
        print('Dirty / uncommitted changes in repository!')
        return True

    return False


def repo_has_outgoing():
    """Checks whether there would be outgoing changesets to the given path"""
    try:
        subprocess.check_output(['hg', 'outgoing'])
        print('Detected outgoing changesets!')
        return True
    except subprocess.CalledProcessError as e:
        if e.returncode == 1:
            return False
        raise


def repo_has_incoming(*repo_paths):
    """Checks whether the local repositories are up-to-date"""
    incoming = False

    for repo_path in repo_paths:
        try:
            subprocess.check_output(['hg', 'incoming', '-R', repo_path])
            print('Detected incoming changesets in "{}"'.format(repo_path))
            incoming = True
        except subprocess.CalledProcessError as e:
            if e.returncode != 1:
                raise

    return incoming


def continue_with_outgoing():
    """Asks the user if they want to continue despite facing warnings"""

    print('If you proceed with the release, they will be included in the '
          'release and pushed.')
    print('Are you sure about continuing the release process?')

    while True:
        choice = raw_input('Please choose (yes / no): ').lower().strip()

        if choice == 'yes':
            return True
        if choice == 'no':
            return False


def can_safely_release(*repo_paths):
    """Run repository-checks in order to bail out early if necessary"""
    if repo_has_uncommitted():
        return False
    if repo_has_incoming(*repo_paths):
        return False
    if repo_has_outgoing():
        return continue_with_outgoing()
    return True


def compare_versions(a, b):
    """Compare two version numbers."""
    a_digits = [int(v) for v in a.split('.')]
    b_digits = [int(v) for v in b.split('.')]

    def safe_get(items, index):
        return items[index] if index < len(items) else 0

    for i in range(max(len(a_digits), len(b_digits))):
        result = safe_get(a_digits, i) - safe_get(b_digits, i)
        if result != 0:
            return result
    return 0


def release_combination_is_possible(version, platforms, base_dir):
    """Determine whether a release for the given parameters is possible.

    Examine existing tags in order to find either higher or matching versions.
    The release is impossible if a) a higher version for a requested platform
    exists, or if b) a matching version exists and the requested set of
    platforms differs from what was already released.
    """
    def higher_tag_version(tag, version, platforms):
        return (compare_versions(tag[0], version) > 0 and
                set(tag[1:]).intersection(platforms))

    def incomplete_platforms_for_version(tag, version, platforms):
        intersection = set(tag[1:]).intersection(platforms)
        return (compare_versions(tag[0], version) == 0 and
                intersection and set(platforms) != set(tag[1:]))

    # only consider tags of the form "1.2[.x ...]-platform[-platform ...]
    platform_tags = re.compile(r'^(\d+(?:(?:\.\d+)*)(?:-\w+)+)$', re.MULTILINE)
    tags = [
        c for c in [
            t.split('-') for t in
            platform_tags.findall(subprocess.check_output(
                ['hg', 'tags', '-R', base_dir, '-q']))
        ] if compare_versions(c[0], version) >= 0
    ]

    for tag in tags:
        if higher_tag_version(tag, version, platforms):
            reason = ('The higher version {} has already been released for '
                      'the platforms {}.').format(tag[0], ', '.join(platforms))
            return False, reason, None

        if incomplete_platforms_for_version(tag, version, platforms):
            reason = ('You have to re-release version {} for exactly all '
                      'of: {}').format(version, ', '.join(tag[1:]))
            return False, reason, None

    return (True, None,
            any(compare_versions(tag[0], version) == 0 for tag in tags))


def update_metadata(metadata, version):
    """Replace version number in metadata file "manually".

    The ConfigParser would mess up the order of lines.
    """
    with open(metadata.option_source('general', 'version'), 'r+b') as fp:
        rawMetadata = fp.read()
        rawMetadata = re.sub(
            r'^(\s*version\s*=\s*).*', r'\g<1>%s' % version,
            rawMetadata, flags=re.I | re.M,
        )

        fp.seek(0)
        fp.write(rawMetadata)
        fp.truncate()


def create_build(platform, base_dir, target_path, version, key_file=None):
    """Create a build for the target platform and version."""
    if platform == 'edge':
        import buildtools.packagerEdge as packager
    else:
        import buildtools.packagerChrome as packager

    metadata = readMetadata(base_dir, platform)
    update_metadata(metadata, version)

    build_path = os.path.join(
        target_path,
        getDefaultFileName(metadata, version,
                           get_extension(platform, key_file is not None)),
    )

    packager.createBuild(base_dir, type=platform, outFile=build_path,
                         releaseBuild=True, keyFile=key_file)

    return build_path


def release_commit(base_dir, extension_name, version, platforms):
    """Create a release commit with a representative message."""
    subprocess.check_output([
        'hg', 'commit', '-R', base_dir, '-m',
        'Noissue - Releasing {} {} for {}'.format(
            extension_name, version,
            ', '.join([p.capitalize() for p in platforms]))],
        stderr=subprocess.STDOUT)


def release_tag(base_dir, tag_name, extension_name):
    """Create a tag, along with a commit message for that tag."""
    subprocess.check_call([
        'hg', 'tag', '-R', base_dir, '-f', tag_name,
        '-m', 'Noissue - Adding release tag for {} {}'.format(
            extension_name, tag_name)])


def run(baseDir, platforms, version, keyFile, downloads_repo):
    if not can_safely_release(baseDir, downloads_repo):
        print('Aborting release.')
        return 1

    target_platforms = sorted(platforms)
    release_identifier = '-'.join([version] + [p for p in target_platforms])

    release_possible, reason, re_release = release_combination_is_possible(
        version, platforms, baseDir)

    if not release_possible:
        logging.error(reason)
        return 2

    downloads = []
    # Read extension name from first provided platform
    locale_config = read_locale_config(
        baseDir, target_platforms[0],
        readMetadata(baseDir, target_platforms[0]))
    default_locale_path = os.path.join(locale_config['base_path'],
                                       locale_config['default_locale'],
                                       'messages.json')
    with open(default_locale_path, 'r') as fp:
        extension_name = json.load(fp)['name']['message']

    for platform in target_platforms:
        used_key_file = None
        if platform == 'chrome':
            # Currently, only chrome builds are provided by us as signed
            # packages. Create an unsigned package in base_dir which should be
            # uploaded to the Chrome Web Store
            create_build(platform, baseDir, baseDir, version)
            used_key_file = keyFile

        downloads.append(
            create_build(platform, baseDir, downloads_repo, version,
                         used_key_file),
        )

    # Only create one commit, one tag and one source archive for all
    # platforms
    archive_path = os.path.join(
        downloads_repo,
        'adblockplus-{}-source.tgz'.format(release_identifier),
    )
    create_sourcearchive(baseDir, archive_path)
    downloads.append(archive_path)
    try:
        release_commit(baseDir, extension_name, version, target_platforms)
    except subprocess.CalledProcessError as e:
        if not (re_release and 'nothing changed' in e.output):
            raise

    release_tag(baseDir, release_identifier, extension_name)

    # Now add the downloads and commit
    subprocess.check_call(['hg', 'add', '-R', downloads_repo] + downloads)
    release_commit(downloads_repo, extension_name, version, target_platforms)

    # Push all changes
    subprocess.check_call(['hg', 'push', '-R', baseDir])
    subprocess.check_call(['hg', 'push', '-R', downloads_repo])
