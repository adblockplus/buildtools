# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

import re
import os
import sys
import codecs
import json
import urlparse
import urllib
import urllib2
import mimetypes
from StringIO import StringIO
from ConfigParser import SafeConfigParser
from zipfile import ZipFile
from xml.parsers.expat import ParserCreate, XML_PARAM_ENTITY_PARSING_ALWAYS

CROWDIN_LANG_MAPPING = {
    'br': 'br-FR',
    'dsb': 'dsb-DE',
    'es': 'es-ES',
    'fur': 'fur-IT',
    'fy': 'fy-NL',
    'ga': 'ga-IE',
    'gu': 'gu-IN',
    'hsb': 'hsb-DE',
    'hy': 'hy-AM',
    'ml': 'ml-IN',
    'nn': 'nn-NO',
    'pa': 'pa-IN',
    'rm': 'rm-CH',
    'si': 'si-LK',
    'sv': 'sv-SE',
    'ur': 'ur-PK',
}

CROWDIN_AP_URL = 'https://api.crowdin.com/api/project'
FIREFOX_RELEASES_URL = 'http://www.mozilla.org/en-US/firefox/all.html'
FIREFOX_LP_URL = 'https://addons.mozilla.org/en-US/firefox/language-tools/'
CHROMIUM_DEB_URL = 'https://packages.debian.org/sid/all/chromium-l10n/filelist'


def read_locale_config(baseDir, platform, metadata):
    if platform != 'generic':
        import buildtools.packagerChrome as packager
        localeDir = os.path.join(baseDir, 'adblockplusui', 'locale')
        localeConfig = {
            'default_locale': packager.defaultLocale,
        }
    else:
        localeDir = os.path.join(
            baseDir, *metadata.get('locales', 'base_path').split('/')
        )
        localeConfig = {
            'default_locale': metadata.get('locales', 'default_locale'),
        }

    localeConfig['base_path'] = localeDir

    locales = [(locale.replace('_', '-'), os.path.join(localeDir, locale))
               for locale in os.listdir(localeDir)]
    localeConfig['locales'] = dict(locales)

    return localeConfig


def crowdin_request(project_name, action, key, get={}, post_data=None,
                    headers={}, raw=False):
    """Perform a call to crowdin and raise an Exception on failure."""
    request = urllib2.Request(
        '{}/{}/{}?{}'.format(CROWDIN_AP_URL,
                             urllib.quote(project_name),
                             urllib.quote(action),
                             urllib.urlencode(dict(get, key=key, json=1))),
        post_data,
        headers,
    )

    try:
        result = urllib2.urlopen(request).read()
    except urllib2.HTTPError as e:
        raise Exception('Server returned HTTP Error {}:\n{}'.format(e.code,
                                                                    e.read()))

    if not raw:
        return json.loads(result)

    return result


def preprocessChromeLocale(path, metadata, isMaster):
    fileHandle = codecs.open(path, 'rb', encoding='utf-8')
    data = json.load(fileHandle)
    fileHandle.close()

    for key, value in data.iteritems():
        if isMaster:
            # Make sure the key name is listed in the description
            if 'description' in value:
                value['description'] = '%s: %s' % (key, value['description'])
            else:
                value['description'] = key
        else:
            # Delete description from translations
            if 'description' in value:
                del value['description']

    return json.dumps(data, ensure_ascii=False, sort_keys=True, indent=2)


def postprocessChromeLocale(path, data):
    parsed = json.loads(data)
    if isinstance(parsed, list):
        return

    # Delete description from translations
    for key, value in parsed.iteritems():
        if 'description' in value:
            del value['description']

    file = codecs.open(path, 'wb', encoding='utf-8')
    json.dump(parsed, file, ensure_ascii=False, sort_keys=True, indent=2, separators=(',', ': '))
    file.close()


def setupTranslations(localeConfig, projectName, key):
    locales = set()

    # Languages supported by Firefox
    data = urllib2.urlopen(FIREFOX_RELEASES_URL).read()
    for match in re.finditer(r'&amp;lang=([\w\-]+)"', data):
        locales.add(match.group(1))

    # Languages supported by Firefox Language Packs
    data = urllib2.urlopen(FIREFOX_LP_URL).read()
    for match in re.finditer(r'<tr>.*?</tr>', data, re.S):
        if match.group(0).find('Install Language Pack') >= 0:
            match2 = re.search(r'lang="([\w\-]+)"', match.group(0))
            if match2:
                locales.add(match2.group(1))

    # Languages supported by Chrome (excluding es-419)
    data = urllib2.urlopen(CHROMIUM_DEB_URL).read()
    for match in re.finditer(r'locales/(?!es-419)([\w\-]+)\.pak', data):
        locales.add(match.group(1))

    # We don't translate indvidual dialects of languages
    # other than English, Spanish, Portuguese and Chinese.
    for locale in list(locales):
        prefix = locale.split('-')[0]
        if prefix not in {'en', 'es', 'pt', 'zh'}:
            locales.remove(locale)
            locales.add(prefix)

    # Add languages with existing translations.
    locales.update(localeConfig['locales'])

    # Don't add the language we translate from as target translation.
    locales.remove(localeConfig['default_locale'].replace('_', '-'))

    # Convert to locales understood by Crowdin.
    locales = {CROWDIN_LANG_MAPPING.get(locale, locale) for locale in locales}
    allowed = {locale['crowdin_code'] for locale in
               crowdin_request(projectName, 'supported-languages', key)}
    if not allowed.issuperset(locales):
        print "Warning, following locales aren't allowed by server: " + ', '.join(locales - allowed)

    locales = sorted(locales & allowed)
    params = urllib.urlencode([('languages[]', locale) for locale in locales])
    crowdin_request(projectName, 'edit-project', key, post_data=params)


def crowdin_prepare_upload(files):
    """Create a post body and matching headers, which Crowdin can handle."""
    boundary = '----------ThIs_Is_tHe_bouNdaRY_$'
    body = ''
    for name, data in files:
        body += (
            '--{boundary}\r\n'
            'Content-Disposition: form-data; name="files[{name}]"; '
            'filename="{name}"\r\n'
            'Content-Type: {mimetype}; charset=utf-8\r\n'
            'Content-Transfer-Encoding: binary\r\n'
            '\r\n{data}\r\n'
            '--{boundary}--\r\n'
        ).format(boundary=boundary,
                 name=name,
                 data=data.encode('utf-8'),
                 mimetype=mimetypes.guess_type(name)[0])

    return (
        StringIO(body),
        {
            'Content-Type': 'multipart/form-data; boundary=' + boundary,
            'Content-Length': len(body),
        },
    )


def updateTranslationMaster(localeConfig, metadata, dir, projectName, key):
    result = crowdin_request(projectName, 'info', key)

    existing = set(map(lambda f: f['name'], result['files']))
    add = []
    update = []
    for file in os.listdir(dir):
        path = os.path.join(dir, file)
        if os.path.isfile(path):
            if file.endswith('.json'):
                data = preprocessChromeLocale(path, metadata, True)
                newName = file
            else:
                fileHandle = codecs.open(path, 'rb', encoding='utf-8')
                data = json.dumps({file: {'message': fileHandle.read()}})
                fileHandle.close()
                newName = file + '.json'

            if data:
                if newName in existing:
                    update.append((newName, data))
                    existing.remove(newName)
                else:
                    add.append((newName, data))

    if len(add):
        query = {'titles[{}]'.format(name): os.path.splitext(name)[0]
                 for name, _ in add}
        query['type'] = 'chrome'
        data, headers = crowdin_prepare_upload(add)
        crowdin_request(projectName, 'add-file', key, query, post_data=data,
                        headers=headers)
    if len(update):
        data, headers = crowdin_prepare_upload(update)
        crowdin_request(projectName, 'update-file', key, post_data=data,
                        headers=headers)
    for file in existing:
        crowdin_request(projectName, 'delete-file', key, {'file': file})


def uploadTranslations(localeConfig, metadata, dir, locale, projectName, key):
    files = []
    for file in os.listdir(dir):
        path = os.path.join(dir, file)
        if os.path.isfile(path):
            if file.endswith('.json'):
                data = preprocessChromeLocale(path, metadata, False)
                newName = file
            else:
                fileHandle = codecs.open(path, 'rb', encoding='utf-8')
                data = json.dumps({file: {'message': fileHandle.read()}})
                fileHandle.close()
                newName = file + '.json'

            if data:
                files.append((newName, data))
    if len(files):
        language = CROWDIN_LANG_MAPPING.get(locale, locale)
        data, headers = crowdin_prepare_upload(files)
        crowdin_request(projectName, 'upload-translation', key,
                        {'language': language}, post_data=data,
                        headers=headers)


def getTranslations(localeConfig, projectName, key):
    """Download all available translations from crowdin.

    Trigger crowdin to build the available export, wait for crowdin to
    finish the job and download the generated zip afterwards.
    """
    crowdin_request(projectName, 'export', key)

    result = crowdin_request(projectName, 'download/all.zip', key, raw=True)
    zip = ZipFile(StringIO(result))
    dirs = {}

    normalizedDefaultLocale = localeConfig['default_locale'].replace('_', '-')
    normalizedDefaultLocale = CROWDIN_LANG_MAPPING.get(normalizedDefaultLocale,
                                                       normalizedDefaultLocale)

    for info in zip.infolist():
        if not info.filename.endswith('.json'):
            continue

        dir, file = os.path.split(info.filename)
        if not re.match(r'^[\w\-]+$', dir) or dir == normalizedDefaultLocale:
            continue
        if file.count('.') == 1:
            origFile = file
        else:
            origFile = os.path.splitext(file)[0]

        for key, value in CROWDIN_LANG_MAPPING.iteritems():
            if value == dir:
                dir = key
        dir = dir.replace('-', '_')

        data = zip.open(info.filename).read()
        if data == '[]':
            continue

        if not dir in dirs:
            dirs[dir] = set()
        dirs[dir].add(origFile)

        path = os.path.join(localeConfig['base_path'], dir, origFile)
        if not os.path.exists(os.path.dirname(path)):
            os.makedirs(os.path.dirname(path))
        if file.endswith('.json'):
            postprocessChromeLocale(path, data)
        else:
            data = json.loads(data)
            if origFile in data:
                fileHandle = codecs.open(path, 'wb', encoding='utf-8')
                fileHandle.write(data[origFile]['message'])
                fileHandle.close()

    # Remove any extra files
    for dir, files in dirs.iteritems():
        baseDir = os.path.join(localeConfig['base_path'], dir)
        if not os.path.exists(baseDir):
            continue
        for file in os.listdir(baseDir):
            path = os.path.join(baseDir, file)
            valid_extension = file.endswith('.json')
            if os.path.isfile(path) and valid_extension and not file in files:
                os.remove(path)
