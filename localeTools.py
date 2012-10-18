# coding: utf-8

# This Source Code is subject to the terms of the Mozilla Public License
# version 2.0 (the "License"). You can obtain a copy of the License at
# http://mozilla.org/MPL/2.0/.

import re, os, sys, codecs, json, urllib, urllib2
from StringIO import StringIO
from ConfigParser import SafeConfigParser
from zipfile import ZipFile
from xml.parsers.expat import ParserCreate, XML_PARAM_ENTITY_PARSING_ALWAYS

langMappingGecko = {
  'dsb': 'dsb-DE',
  'hsb': 'hsb-DE',
}

langMappingChrome = {
  'es-419': 'es-AR',
  'es': 'es-ES',
  'sv': 'sv-SE',
  'ml': 'ml-IN',
  'nb': 'no',
}

chromeLocales = [
  "am",
  "ar",
  "bg",
  "bn",
  "ca",
  "cs",
  "da",
  "de",
  "el",
  "en-GB",
  "en-US",
  "es-419",
  "es",
  "et",
  "fa",
  "fi",
  "fil",
  "fr",
  "gu",
  "he",
  "hi",
  "hr",
  "hu",
  "id",
  "it",
  "ja",
  "kn",
  "ko",
  "lt",
  "lv",
  "ml",
  "mr",
  "ms",
  "nb",
  "nl",
  "pl",
  "pt-BR",
  "pt-PT",
  "ro",
  "ru",
  "sk",
  "sl",
  "sr",
  "sv",
  "sw",
  "ta",
  "te",
  "th",
  "tr",
  "uk",
  "vi",
  "zh-CN",
  "zh-TW",
]

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

def appendToFile(path, key, value):
  fileHandle = codecs.open(path, 'ab', encoding='utf-8')
  fileHandle.write(generateStringEntry(key, value, path))
  fileHandle.close()

def removeFromFile(path, key):
  fileHandle = codecs.open(path, 'rb', encoding='utf-8')
  data = fileHandle.read()
  fileHandle.close()

  if path.endswith('.dtd'):
    data = re.sub(r'<!ENTITY\s+%s\s+"[^"]*">\s*' % key, '', data, re.S)
  else:
    data = re.sub(r'(^|\n)%s=[^\n]*\n' % key, r'\1', data, re.S)

  fileHandle = codecs.open(path, 'wb', encoding='utf-8')
  fileHandle.write(data)
  fileHandle.close()

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
  return json.dumps(result, indent=2)

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

def setupTranslations(type, locales, projectName, key):
  # Copy locales list, we don't want to change the parameter
  locales = set(locales)

  # Fill up with locales that we don't have but the browser supports
  if type == 'chrome':
    for locale in chromeLocales:
      locales.add(locale)
  else:
    firefoxLocales = urllib2.urlopen('http://www.mozilla.org/en-US/firefox/all.html').read()
    for match in re.finditer(r'&amp;lang=([\w\-]+)"', firefoxLocales):
      locales.add(langMappingGecko.get(match.group(1), match.group(1)))
    langPacks = urllib2.urlopen('https://addons.mozilla.org/en-US/firefox/language-tools/').read()
    for match in re.finditer(r'<tr>.*?</tr>', langPacks, re.S):
      if match.group(0).find('Install Language Pack') >= 0:
        match2 = re.search(r'lang="([\w\-]+)"', match.group(0))
        if match2:
          locales.add(langMappingGecko.get(match2.group(1), match2.group(1)))

  # Convert locale codes to the ones that Crowdin will understand
  mapping = langMappingChrome if type == 'chrome' else langMappingGecko
  locales = set(map(lambda locale: mapping[locale] if locale in mapping else locale, locales))

  allowed = set()
  allowedLocales = urllib2.urlopen('http://crowdin.net/page/language-codes').read()
  for match in re.finditer(r'<tr>\s*<td>([\w\-]+)</td>', allowedLocales, re.S):
    allowed.add(match.group(1))
  if not allowed.issuperset(locales):
    print 'Warning, following locales aren\'t allowed by server: ' + ', '.join(locales - allowed)

  locales = list(locales & allowed)
  locales.sort()
  params = urllib.urlencode([('languages[]', locale) for locale in locales])
  result = urllib2.urlopen('http://api.crowdin.net/api/project/%s/edit-project?key=%s&%s' % (projectName, key, params)).read()
  if result.find('<success') < 0:
    raise Exception('Server indicated that the operation was not successful\n' + result)

def updateTranslationMaster(dir, locale, projectName, key):
  result = json.load(urllib2.urlopen('http://api.crowdin.net/api/project/%s/info?key=%s&json=1' % (projectName, key)))

  existing = set(map(lambda f: f['name'], result['files']))
  add = []
  update = []
  for file in os.listdir(dir):
    path = os.path.join(dir, file)
    if os.path.isfile(path):
      data = toJSON(path)
      if data:
        newName = file + '.json'
        if newName in existing:
          update.append((newName, data))
          existing.remove(newName)
        else:
          add.append((newName, data))

  def postFiles(files, url):
    boundary = '----------ThIs_Is_tHe_bouNdaRY_$'
    body = ''
    for file, data in files:
      body +=  '--%s\r\n' % boundary
      body += 'Content-Disposition: form-data; name="files[%s]"; filename="%s"\r\n' % (file, file)
      body += 'Content-Type: application/octet-stream\r\n'
      body += '\r\n' + data.encode('utf-8') + '\r\n'
      body += '--%s--\r\n' % boundary

    request = urllib2.Request(url, body)
    request.add_header('Content-Type', 'multipart/form-data; boundary=%s' % boundary)
    request.add_header('Content-Length', len(body))
    result = urllib2.urlopen(request).read()
    if result.find('<success') < 0:
      raise Exception('Server indicated that the operation was not successful\n' + result)

  if len(add):
    titles = urllib.urlencode([('titles[%s]' % name, re.sub(r'\.json', '', name)) for name, data in add])
    postFiles(add, 'http://api.crowdin.net/api/project/%s/add-file?key=%s&type=chrome&%s' % (projectName, key, titles))
  if len(update):
    postFiles(update, 'http://api.crowdin.net/api/project/%s/update-file?key=%s' % (projectName, key))
  for file in existing:
    result = urllib2.urlopen('http://api.crowdin.net/api/project/%s/delete-file?key=%s&file=%s' % (projectName, key, file)).read()
    if result.find('<success') < 0:
      raise Exception('Server indicated that the operation was not successful\n' + result)

def getTranslations(localesDir, defaultLocale, projectName, key):
  result = urllib2.urlopen('http://api.crowdin.net/api/project/%s/export?key=%s' % (projectName, key)).read()
  if result.find('<success') < 0:
    raise Exception('Server indicated that the operation was not successful\n' + result)

  result = urllib2.urlopen('http://api.crowdin.net/api/project/%s/download/all.zip?key=%s' % (projectName, key)).read()
  zip = ZipFile(StringIO(result))
  dirs = {}
  for info in zip.infolist():
    if not info.filename.endswith('.dtd.json') and not info.filename.endswith('.properties.json'):
      continue

    dir, file = os.path.split(info.filename)
    origFile = re.sub(r'\.json$', '', file)
    if not re.match(r'^[\w\-]+$', dir) or dir == defaultLocale:
      continue

    for key, value in langMappingGecko.iteritems():
      if value == dir:
        dir = key

    if not dir in dirs:
      dirs[dir] = set()
    dirs[dir].add(origFile)

    data = zip.open(info.filename).read()
    fromJSON(os.path.join(localesDir, dir, origFile), data)

  # Remove any extra files
  for dir, files in dirs.iteritems():
    baseDir = os.path.join(localesDir, dir)
    if not os.path.exists(baseDir):
      continue
    for file in os.listdir(baseDir):
      path = os.path.join(baseDir, file)
      if os.path.isfile(path) and (file.endswith('.properties') or file.endswith('.dtd')) and not file in files:
        os.remove(path)
