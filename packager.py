# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

# Note: These are the base functions common to all packagers, the actual
# packagers are implemented in packagerChrome and packagerEdge.

import sys
import os
import re
import subprocess
import json
import zipfile
from StringIO import StringIO
from chainedconfigparser import ChainedConfigParser

import buildtools

EXTENSIONS = {
    'edge': 'appx',
    'gecko': 'xpi',
    'chrome': {'unsigned': 'zip', 'signed': 'crx'},
}


def getDefaultFileName(metadata, version, ext):
    return '%s-%s.%s' % (metadata.get('general', 'basename'), version, ext)


def get_extension(platform, has_key_file=False):
    extension = EXTENSIONS[platform]

    try:
        if has_key_file:
            key = 'signed'
        else:
            key = 'unsigned'
        extension = extension[key]
    except (KeyError, TypeError):
        pass

    return extension


def get_build_specific_option(release_build, metadata, prefix):
    suffix = 'release' if release_build else 'devbuild'
    return metadata.get('general', '{}_{}'.format(prefix, suffix))


def get_app_id(release_build, metadata):
    return get_build_specific_option(release_build, metadata, 'app_id')


def getMetadataPath(baseDir, type):
    return os.path.join(baseDir, 'metadata.%s' % type)


def getDevEnvPath(baseDir, type):
    return os.path.join(baseDir, 'devenv.' + type)


def readMetadata(baseDir, type):
    parser = ChainedConfigParser()
    parser.optionxform = lambda option: option
    parser.read(getMetadataPath(baseDir, type))
    return parser


def getBuildNum(baseDir):
    try:
        from buildtools.ensure_dependencies import Mercurial, Git
        if Mercurial().istype(baseDir):
            result = subprocess.check_output(['hg', 'id', '-R', baseDir, '-n'])
            return re.sub(r'\D', '', result)
        elif Git().istype(baseDir):
            result = subprocess.check_output(
                ['git', 'rev-list', '--count', '--branches', '--tags'],
                cwd=baseDir,
            )
            return result.strip()
    except subprocess.CalledProcessError:
        pass

    return '0'


def getBuildVersion(baseDir, metadata, releaseBuild, buildNum=None):
    version = metadata.get('general', 'version')
    if not releaseBuild:
        if buildNum == None:
            buildNum = getBuildNum(baseDir)
        if len(buildNum) > 0:
            if re.search(r'(^|\.)\d+$', version):
                # Numerical version number - need to fill up with zeros to have three
                # version components.
                while version.count('.') < 2:
                    version += '.0'
            version += '.' + buildNum
    return version


def getTemplate(template, autoEscape=False):
    import jinja2

    template_path = os.path.join(buildtools.__path__[0], 'templates')
    loader = jinja2.FileSystemLoader(template_path)
    if autoEscape:
        env = jinja2.Environment(loader=loader, autoescape=True)
    else:
        env = jinja2.Environment(loader=loader)
    env.filters.update({'json': json.dumps})
    return env.get_template(template)


class Files(dict):
    def __init__(self, includedFiles, ignoredFiles, process=None):
        self.includedFiles = includedFiles
        self.ignoredFiles = ignoredFiles
        self.process = process

    def __setitem__(self, key, value):
        if self.process:
            value = self.process(key, value)
        dict.__setitem__(self, key, value)

    def isIncluded(self, relpath):
        return relpath.split('/')[0] in self.includedFiles

    def is_ignored(self, relpath):
        parts = relpath.split('/')
        return any(part in self.ignoredFiles for part in parts)

    def read(self, path, relpath='', skip=()):
        if os.path.isdir(path):
            for file in os.listdir(path):
                name = relpath + ('/' if relpath != '' else '') + file
                included = self.isIncluded(name) and not self.is_ignored(name)
                if name not in skip and included:
                    self.read(os.path.join(path, file), name, skip)
        else:
            with open(path, 'rb') as file:
                if relpath in self:
                    print >>sys.stderr, 'Warning: File %s defined multiple times' % relpath
                self[relpath] = file.read()

    def readMappedFiles(self, mappings):
        for item in mappings:
            target, source = item

            if '/' in target and self.is_ignored(target):
                continue

            parts = source.split('/')
            path = os.path.join(os.path.dirname(item.source), *parts)
            if os.path.exists(path):
                self.read(path, target)
            else:
                print >>sys.stderr, "Warning: Mapped file %s doesn't exist" % source

    def preprocess(self, filenames, params={}):
        import jinja2
        env = jinja2.Environment()

        for filename in filenames:
            env.autoescape = os.path.splitext(filename)[1].lower() in ('.html', '.xml')
            template = env.from_string(self[filename].decode('utf-8'))
            self[filename] = template.render(params).encode('utf-8')

    def zip(self, outFile, sortKey=None, compression=zipfile.ZIP_DEFLATED):
        with zipfile.ZipFile(outFile, 'w', compression) as zf:
            for name in sorted(self, key=sortKey):
                zf.writestr(name, self[name])

    def zipToString(self, sortKey=None):
        buffer = StringIO()
        self.zip(buffer, sortKey=sortKey)
        return buffer.getvalue()
