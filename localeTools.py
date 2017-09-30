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

langMappingGecko = {
    'bn-BD': 'bn',
    'br': 'br-FR',
    'dsb': 'dsb-DE',
    'fj-FJ': 'fj',
    'hsb': 'hsb-DE',
    'hi-IN': 'hi',
    'ml': 'ml-IN',
    'nb-NO': 'nb',
    'rm': 'rm-CH',
    'ta-LK': 'ta',
    'wo-SN': 'wo',
}

langMappingChrome = {
    'es-419': 'es-MX',
    'es': 'es-ES',
    'sv': 'sv-SE',
    'ml': 'ml-IN',
    'gu': 'gu-IN',
}

chromeLocales = [
    'am',
    'ar',
    'bg',
    'bn',
    'ca',
    'cs',
    'da',
    'de',
    'el',
    'en-GB',
    'en-US',
    'es-419',
    'es',
    'et',
    'fa',
    'fi',
    'fil',
    'fr',
    'gu',
    'he',
    'hi',
    'hr',
    'hu',
    'id',
    'it',
    'ja',
    'kn',
    'ko',
    'lt',
    'lv',
    'ml',
    'mr',
    'ms',
    'nb',
    'nl',
    'pl',
    'pt-BR',
    'pt-PT',
    'ro',
    'ru',
    'sk',
    'sl',
    'sr',
    'sv',
    'sw',
    'ta',
    'te',
    'th',
    'tr',
    'uk',
    'vi',
    'zh-CN',
    'zh-TW',
]

CROWDIN_AP_URL = 'https://api.crowdin.com/api/project'


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


class OrderedDict(dict):
    def __init__(self):
        self.__order = []

    def __setitem__(self, key, value):
        self.__order.append(key)
        dict.__setitem__(self, key, value)

    def iteritems(self):
        done = set()
        for key in self.__order:
            if not key in done and key in self:
                yield (key, self[key])
                done.add(key)


def escapeEntity(value):
    return value.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;').replace('"', '&quot;')


def unescapeEntity(value):
    return value.replace('&amp;', '&').replace('&lt;', '<').replace('&gt;', '>').replace('&quot;', '"')


def mapLocale(type, locale):
    mapping = langMappingChrome if type == 'ISO-15897' else langMappingGecko
    return mapping.get(locale, locale)


def parseDTDString(data, path):
    result = []
    currentComment = [None]

    parser = ParserCreate()
    parser.UseForeignDTD(True)
    parser.SetParamEntityParsing(XML_PARAM_ENTITY_PARSING_ALWAYS)

    def ExternalEntityRefHandler(context, base, systemId, publicId):
        subparser = parser.ExternalEntityParserCreate(context, 'utf-8')
        subparser.Parse(data.encode('utf-8'), True)
        return 1

    def CommentHandler(data):
        currentComment[0] = data.strip()

    def EntityDeclHandler(entityName, is_parameter_entity, value, base, systemId, publicId, notationName):
        result.append((unescapeEntity(entityName), currentComment[0], unescapeEntity(value.strip())))
        currentComment[0] = None

    parser.ExternalEntityRefHandler = ExternalEntityRefHandler
    parser.CommentHandler = CommentHandler
    parser.EntityDeclHandler = EntityDeclHandler
    parser.Parse('<!DOCTYPE root SYSTEM "foo"><root/>', True)

    for entry in result:
        yield entry


def escapeProperty(value):
    return value.replace('\n', '\\n')


def unescapeProperty(value):
    return value.replace('\\n', '\n')


def parsePropertiesString(data, path):
    currentComment = None
    for line in data.splitlines():
        match = re.search(r'^\s*[#!]\s*(.*)', line)
        if match:
            currentComment = match.group(1)
        elif '=' in line:
            key, value = line.split('=', 1)
            yield (unescapeProperty(key), currentComment, unescapeProperty(value))
            currentComment = None
        elif re.search(r'\S', line):
            print >>sys.stderr, 'Unrecognized data in file %s: %s' % (path, line)


def parseString(data, path):
    result = {'_origData': data}
    if path.endswith('.dtd'):
        it = parseDTDString(data, path)
    elif path.endswith('.properties'):
        it = parsePropertiesString(data, path)
    else:
        return None

    for name, comment, value in it:
        result[name] = value
    return result


def readFile(path):
    fileHandle = codecs.open(path, 'rb', encoding='utf-8')
    data = fileHandle.read()
    fileHandle.close()
    return parseString(data, path)


def generateStringEntry(key, value, path):
    if path.endswith('.dtd'):
        return '<!ENTITY %s "%s">\n' % (escapeEntity(key), escapeEntity(value))
    else:
        return '%s=%s\n' % (escapeProperty(key), escapeProperty(value))


def toJSON(path):
    fileHandle = codecs.open(path, 'rb', encoding='utf-8')
    data = fileHandle.read()
    fileHandle.close()

    if path.endswith('.dtd'):
        it = parseDTDString(data, path)
    elif path.endswith('.properties'):
        it = parsePropertiesString(data, path)
    else:
        return None

    result = OrderedDict()
    for name, comment, value in it:
        obj = {'message': value}
        if comment == None:
            obj['description'] = name
        else:
            obj['description'] = '%s: %s' % (name, comment)
        result[name] = obj
    return json.dumps(result, ensure_ascii=False, indent=2)


def fromJSON(path, data):
    data = json.loads(data)
    if not data:
        if os.path.exists(path):
            os.remove(path)
        return

    dir = os.path.dirname(path)
    if not os.path.exists(dir):
        os.makedirs(dir)
    file = codecs.open(path, 'wb', encoding='utf-8')
    for key, value in data.iteritems():
        file.write(generateStringEntry(key, value['message'], path))
    file.close()


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
    # Make a new set from the locales list, mapping to Crowdin friendly format
    locales = {mapLocale(localeConfig['name_format'], locale)
               for locale in localeConfig['locales']}

    # Fill up with locales that we don't have but the browser supports
    if 'chrome' in localeConfig['target_platforms']:
        for locale in chromeLocales:
            locales.add(mapLocale('ISO-15897', locale))

    if 'gecko' in localeConfig['target_platforms']:
        firefoxLocales = urllib2.urlopen('http://www.mozilla.org/en-US/firefox/all.html').read()
        for match in re.finditer(r'&amp;lang=([\w\-]+)"', firefoxLocales):
            locales.add(mapLocale('BCP-47', match.group(1)))
        langPacks = urllib2.urlopen('https://addons.mozilla.org/en-US/firefox/language-tools/').read()
        for match in re.finditer(r'<tr>.*?</tr>', langPacks, re.S):
            if match.group(0).find('Install Language Pack') >= 0:
                match2 = re.search(r'lang="([\w\-]+)"', match.group(0))
                if match2:
                    locales.add(mapLocale('BCP-47', match2.group(1)))

    allowed = set()
    allowedLocales = crowdin_request(projectName, 'supported-languages', key)

    for locale in allowedLocales:
        allowed.add(locale['crowdin_code'])
    if not allowed.issuperset(locales):
        print "Warning, following locales aren't allowed by server: " + ', '.join(locales - allowed)

    locales = list(locales & allowed)
    locales.sort()
    params = urllib.urlencode([('languages[]', locale) for locale in locales])

    crowdin_request(projectName, 'edit-project', key, post_data=params)


def crowdin_prepare_upload(files):
    """Create a post body and matching headers, which Crowdin can handle."""
    boundary = '----------ThIs_Is_tHe_bouNdaRY_$'
    body = ''
    for name, data in files:
        mimetype = mimetypes.guess_type(name)[0]
        body += (
            '--{boundary}\r\n'
            'Content-Disposition: form-data; name="files[{name}]"; '
            'filename="{name}"\r\n'
            'Content-Type: {mimetype}; charset=utf-8\r\n'
            'Content-Transfer-Encoding: binary\r\n'
            '\r\n{data}\r\n'
            '--{boundary}--\r\n'
        ).format(boundary=boundary, name=name, data=data, mimetype=mimetype)

    body = body.encode('utf-8')
    return (
        StringIO(body),
        {
            'Content-Type': ('multipart/form-data; boundary=' + boundary),
            'Content-Length': len(body)
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
            if localeConfig['file_format'] == 'chrome-json' and file.endswith('.json'):
                data = preprocessChromeLocale(path, metadata, True)
                newName = file
            elif localeConfig['file_format'] == 'chrome-json':
                fileHandle = codecs.open(path, 'rb', encoding='utf-8')
                data = json.dumps({file: {'message': fileHandle.read()}})
                fileHandle.close()
                newName = file + '.json'
            else:
                data = toJSON(path)
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
            if localeConfig['file_format'] == 'chrome-json' and file.endswith('.json'):
                data = preprocessChromeLocale(path, metadata, False)
                newName = file
            elif localeConfig['file_format'] == 'chrome-json':
                fileHandle = codecs.open(path, 'rb', encoding='utf-8')
                data = json.dumps({file: {'message': fileHandle.read()}})
                fileHandle.close()
                newName = file + '.json'
            else:
                data = toJSON(path)
                newName = file + '.json'

            if data:
                files.append((newName, data))
    if len(files):
        language = mapLocale(localeConfig['name_format'], locale)
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

    normalizedDefaultLocale = localeConfig['default_locale']
    if localeConfig['name_format'] == 'ISO-15897':
        normalizedDefaultLocale = normalizedDefaultLocale.replace('_', '-')
    normalizedDefaultLocale = mapLocale(localeConfig['name_format'],
                                        normalizedDefaultLocale)

    for info in zip.infolist():
        if not info.filename.endswith('.json'):
            continue

        dir, file = os.path.split(info.filename)
        if not re.match(r'^[\w\-]+$', dir) or dir == normalizedDefaultLocale:
            continue
        if localeConfig['file_format'] == 'chrome-json' and file.count('.') == 1:
            origFile = file
        else:
            origFile = re.sub(r'\.json$', '', file)
        if (localeConfig['file_format'] == 'gecko-dtd' and
            not origFile.endswith('.dtd') and
            not origFile.endswith('.properties')):
            continue

        if localeConfig['name_format'] == 'ISO-15897':
            mapping = langMappingChrome
        else:
            mapping = langMappingGecko

        for key, value in mapping.iteritems():
            if value == dir:
                dir = key
        if localeConfig['name_format'] == 'ISO-15897':
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
        if localeConfig['file_format'] == 'chrome-json' and file.endswith('.json'):
            postprocessChromeLocale(path, data)
        elif localeConfig['file_format'] == 'chrome-json':
            data = json.loads(data)
            if origFile in data:
                fileHandle = codecs.open(path, 'wb', encoding='utf-8')
                fileHandle.write(data[origFile]['message'])
                fileHandle.close()
        else:
            fromJSON(path, data)

    # Remove any extra files
    for dir, files in dirs.iteritems():
        baseDir = os.path.join(localeConfig['base_path'], dir)
        if not os.path.exists(baseDir):
            continue
        for file in os.listdir(baseDir):
            path = os.path.join(baseDir, file)
            if os.path.isfile(path) and (file.endswith('.json') or file.endswith('.properties') or file.endswith('.dtd')) and not file in files:
                os.remove(path)
