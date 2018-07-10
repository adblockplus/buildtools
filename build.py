# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

import argparse
import logging
import io
import json
import os
import re
import shutil
import subprocess
import sys
from urllib import urlencode
import urllib2
from functools import partial
from StringIO import StringIO
from zipfile import ZipFile
from buildtools.localeTools import read_locale_config

KNOWN_PLATFORMS = {'chrome', 'gecko', 'edge', 'generic'}

MAIN_PARSER = argparse.ArgumentParser(
    description=__doc__,
    formatter_class=argparse.RawDescriptionHelpFormatter)

SUB_PARSERS = MAIN_PARSER.add_subparsers(title='Commands', dest='action',
                                         metavar='[command]')

ALL_COMMANDS = []


def make_argument(*args, **kwargs):
    def _make_argument(*args, **kwargs):
        parser = kwargs.pop('parser')
        parser.add_argument(*args, **kwargs)

    return partial(_make_argument, *args, **kwargs)


def argparse_command(valid_platforms=None, multi_platform=False,
                     no_platform=False, arguments=()):
    def wrapper(func):
        def func_wrapper(*args, **kwargs):
            return func(*args, **kwargs)

        short_desc, long_desc = func.__doc__.split('\n\n', 1)

        ALL_COMMANDS.append({
            'name': func.__name__,
            'description': long_desc,
            'help_text': short_desc,
            'valid_platforms': valid_platforms or KNOWN_PLATFORMS,
            'multi_platform': multi_platform,
            'function': func,
            'arguments': arguments,
            'no_platform': no_platform,
        })
        return func_wrapper
    return wrapper


def make_subcommand(name, description, help_text, function, arguments):
    new_parser = SUB_PARSERS.add_parser(
        name.replace('_', '-'), description=description, help=help_text,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    for argument in arguments:
        argument(parser=new_parser)

    new_parser.set_defaults(function=function)
    return new_parser


def build_available_subcommands(base_dir):
    """Build subcommands, which are available for the repository in base_dir.

    Search 'base_dir' for existing metadata.<type> files and make <type> an
    avaible choice for the subcommands, intersected with their respective valid
    platforms.

    If no valid platform is found for a subcommand, it get's omitted.
    """
    if build_available_subcommands._result is not None:
        # Tests might run this code multiple times, make sure the collection
        # of platforms is only run once.
        return build_available_subcommands._result

    types = set()
    for p in KNOWN_PLATFORMS:
        if os.path.exists(os.path.join(base_dir, 'metadata.' + p)):
            types.add(p)

    if len(types) == 0:
        logging.error('No metadata file found in this repository. Expecting '
                      'one or more of {} to be present.'.format(
                          ', '.join('metadata.' + p for p in KNOWN_PLATFORMS)))
        build_available_subcommands._result = False
        return False

    for command_params in ALL_COMMANDS:
        multi_platform = command_params.pop('multi_platform')
        no_platform = command_params.pop('no_platform')
        platforms = types.intersection(command_params.pop('valid_platforms'))
        if len(platforms) > 1:
            if multi_platform:
                help_text = ('Multiple types may be specifed (each preceded '
                             'by -t/--type)')
                action = 'append'
            else:
                help_text = None
                action = 'store'
            if not no_platform:
                command_params['arguments'] += (
                    make_argument('-t', '--type', dest='platform',
                                  required=True, choices=platforms,
                                  action=action, help=help_text),
                )
            make_subcommand(**command_params)
        elif len(platforms) == 1:
            sub_parser = make_subcommand(**command_params)
            sub_parser.set_defaults(platform=platforms.pop())

    build_available_subcommands._result = True
    return True


build_available_subcommands._result = None


@argparse_command(
    valid_platforms={'chrome', 'gecko', 'edge'},
    arguments=(
        make_argument(
            '-b', '--build-num', dest='build_num',
            help='Use given build number (if omitted the build number will '
                 'be retrieved from Mercurial)'),
        make_argument(
            '-k', '--key', dest='key_file',
            help='File containing private key and certificates required to '
                  'sign the package'),
        make_argument(
            '-r', '--release', action='store_true',
            help='Create a release build'),
        make_argument('output_file', nargs='?'),
    ),
)
def build(base_dir, build_num, key_file, release, output_file, platform,
          **kwargs):
    """
    Create a build.

    Creates an extension build with given file name. If output_file is missing
    a default name will be chosen.
    """
    kwargs = {}
    if platform == 'edge':
        import buildtools.packagerEdge as packager
    else:
        import buildtools.packagerChrome as packager

    kwargs['keyFile'] = key_file
    kwargs['outFile'] = output_file
    kwargs['releaseBuild'] = release
    kwargs['buildNum'] = build_num

    packager.createBuild(base_dir, type=platform, **kwargs)


@argparse_command(
    valid_platforms={'chrome', 'gecko', 'edge'},
)
def devenv(base_dir, platform, **kwargs):
    """
    Set up a development environment.

    Will set up or update the devenv folder as an unpacked extension folder '
    for development.
    """
    if platform == 'edge':
        import buildtools.packagerEdge as packager
    else:
        import buildtools.packagerChrome as packager

    file = StringIO()
    packager.createBuild(base_dir, type=platform, outFile=file, devenv=True,
                         releaseBuild=True)

    from buildtools.packager import getDevEnvPath
    devenv_dir = getDevEnvPath(base_dir, platform)

    shutil.rmtree(devenv_dir, ignore_errors=True)

    file.seek(0)
    with ZipFile(file, 'r') as zip_file:
        zip_file.extractall(devenv_dir)


project_key_argument = make_argument(
    'project_key', help='The crowdin project key.',
)


@argparse_command(
    arguments=(project_key_argument,),
)
def setuptrans(base_dir, project_key, platform, **kwargs):
    """
    Set up translation languages.

    Set up translation languages for the project on crowdin.com.
    """
    from buildtools.packager import readMetadata
    metadata = readMetadata(base_dir, platform)

    basename = metadata.get('general', 'basename')
    locale_config = read_locale_config(base_dir, platform, metadata)

    import buildtools.localeTools as localeTools
    localeTools.setupTranslations(locale_config, basename, project_key)


@argparse_command(
    arguments=(project_key_argument,),
)
def translate(base_dir, project_key, platform, **kwargs):
    """
    Update translation master files.

    Update the translation master files in the project on crowdin.com.
    """
    from buildtools.packager import readMetadata
    metadata = readMetadata(base_dir, platform)

    basename = metadata.get('general', 'basename')
    locale_config = read_locale_config(base_dir, platform, metadata)

    default_locale_dir = os.path.join(locale_config['base_path'],
                                      locale_config['default_locale'])

    import buildtools.localeTools as localeTools
    localeTools.updateTranslationMaster(locale_config, metadata,
                                        default_locale_dir, basename,
                                        project_key)


@argparse_command(
    arguments=(project_key_argument,),
)
def uploadtrans(base_dir, project_key, platform, **kwargs):
    """
    Upload existing translations.

    Upload already existing translations to the project on crowdin.com.
    """
    from buildtools.packager import readMetadata
    metadata = readMetadata(base_dir, platform)

    basename = metadata.get('general', 'basename')
    locale_config = read_locale_config(base_dir, platform, metadata)

    import buildtools.localeTools as localeTools
    for locale, locale_dir in locale_config['locales'].iteritems():
        if locale != locale_config['default_locale'].replace('_', '-'):
            localeTools.uploadTranslations(locale_config, metadata, locale_dir,
                                           locale, basename, project_key)


@argparse_command(
    arguments=(project_key_argument,),
)
def gettranslations(base_dir, project_key, platform, **kwargs):
    """
    Download translation updates.

    Download updated translations from crowdin.com.
    """
    from buildtools.packager import readMetadata
    metadata = readMetadata(base_dir, platform)

    basename = metadata.get('general', 'basename')
    locale_config = read_locale_config(base_dir, platform, metadata)

    import buildtools.localeTools as localeTools
    localeTools.getTranslations(locale_config, basename, project_key)


@argparse_command(
    valid_platforms={'chrome'},
    arguments=(
        make_argument('target_dir'),
        make_argument('-q', '--quiet', help='Suppress JsDoc output',
                      action='store_true', default=False),
    ),
)
def docs(base_dir, target_dir, quiet, platform, **kwargs):
    """
    Generate documentation (requires node.js).

    Generate documentation files and write them into the specified directory.
    """
    source_dir = os.path.join(base_dir, 'lib')

    # JSDoc struggles wih huge objects:
    # https://github.com/jsdoc3/jsdoc/issues/976
    sources = [os.path.join(source_dir, filename)
               for filename in os.listdir(source_dir)
               if filename != 'publicSuffixList.js']

    buildtools_path = os.path.dirname(__file__)
    config = os.path.join(buildtools_path, 'jsdoc.conf')

    command = ['npm', 'run-script', 'jsdoc', '--', '--destination', target_dir,
               '--configure', config] + sources
    if quiet:
        process = subprocess.Popen(command, stdout=subprocess.PIPE,
                                   stderr=subprocess.PIPE, cwd=buildtools_path)
        stderr = process.communicate()[1]
        retcode = process.poll()
        if retcode:
            sys.stderr.write(stderr)
            raise subprocess.CalledProcessError(command, retcode)
    else:
        subprocess.check_call(command, cwd=buildtools_path)


def valid_version_format(value):
    if re.search(r'[^\d\.]', value):
        raise argparse.ArgumentTypeError('Wrong version number format')

    return value


@argparse_command(
    valid_platforms={'chrome', 'gecko', 'edge'}, multi_platform=True,
    arguments=(
        make_argument(
            '-k', '--key', dest='key_file',
            help='File containing private key and certificates required to '
                  'sign the release.'),
        make_argument(
            '-d', '--downloads-repository', dest='downloads_repository',
            help='Directory containing downloads repository (if omitted '
                  '../downloads is assumed)'),
        make_argument(
            'version', help='Version number of the release',
            type=valid_version_format),
    ),
)
def release(base_dir, downloads_repository, key_file, platform, version,
            **kwargs):
    """
    Run release automation.

    Note: If you are not the project owner then you probably don't want to run
    this!

    Run release automation: create downloads for the new version, tag source
    code repository as well as downloads and buildtools repository.
    """
    if downloads_repository is None:
        downloads_repository = os.path.join(base_dir, os.pardir, 'downloads')

    if 'chrome' in platform and key_file is None:
        logging.error('You must specify a key file for this release')
        return

    import buildtools.releaseAutomation as releaseAutomation
    releaseAutomation.run(base_dir, platform, version, key_file,
                          downloads_repository)


@argparse_command(valid_platforms={'chrome'})
def updatepsl(base_dir, **kwargs):
    """Update Public Suffix List.

    Downloads Public Suffix List (see http://publicsuffix.org/) and generates
    lib/publicSuffixList.js from it.
    """
    import buildtools.publicSuffixListUpdater as publicSuffixListUpdater
    publicSuffixListUpdater.updatePSL(base_dir)


@argparse_command(no_platform=True)
def lint_gitlab_ci(base_dir, **kwargs):
    """Lint the .gitlab-ci.yaml file.

    Test the .gitlab-ci.yaml file for validity. (Note: You need to have PyYAML
    installed.)
    """
    import yaml
    filename = '.gitlab-ci.yml'
    try:
        with io.open(os.path.join(base_dir, filename), 'rt') as fp:
            yaml_data = yaml.load(fp.read())

        post_data = {'content': json.dumps(yaml_data)}
        request = urllib2.Request('https://gitlab.com/api/v4/ci/lint/',
                                  data=urlencode(post_data))
        print urllib2.urlopen(request).read()
    except IOError:
        print 'No valid {} found.'.format(filename)


def process_args(base_dir, *args):
    if build_available_subcommands(base_dir):
        MAIN_PARSER.set_defaults(base_dir=base_dir)

        # If no args are provided, this module is run directly from the command
        # line. argparse will take care of consuming sys.argv.
        arguments = MAIN_PARSER.parse_args(args if len(args) > 0 else None)

        function = arguments.function
        del arguments.function
        function(**vars(arguments))
