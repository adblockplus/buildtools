# coding: utf-8

# This Source Code is subject to the terms of the Mozilla Public License
# version 2.0 (the "License"). You can obtain a copy of the License at
# http://mozilla.org/MPL/2.0/.

import re, os, sys, codecs, json, urllib2
from StringIO import StringIO
from ConfigParser import SafeConfigParser
from xml.parsers.expat import ParserCreate, XML_PARAM_ENTITY_PARSING_ALWAYS

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
    if comment != None:
      obj['description'] = comment
    result[name] = obj
  return json.dumps(result, indent=2)

def updateTranslationMaster(dir, locale, projectName, user, password):
  def encode_multipart_formdata(filename, data):
    boundary = '----------ThIs_Is_tHe_bouNdaRY_$'
    body =  '--%s\r\n' % boundary
    body += 'Content-Disposition: form-data; name="%s"; filename="%s"\r\n' % ('file', filename)
    body += 'Content-Type: application/octet-stream\r\n'
    body += '\r\n' + data + '\r\n'
    body += '--%s--\r\n' % boundary
    content_type = 'multipart/form-data; boundary=%s' % boundary
    return content_type, body

  locale = re.sub(r'-.*', '', locale)
  passman = urllib2.HTTPPasswordMgrWithDefaultRealm()
  passman.add_password(None, 'https://api.getlocalization.com/', user, password)
  opener = urllib2.build_opener(urllib2.HTTPBasicAuthHandler(passman))
  result = json.load(opener.open('https://api.getlocalization.com/%s/api/list-master/json/' % projectName))
  if not result.get('success', 0):
    raise Exception('Server indicated the retrieving the list of masters failed')

  existing = set(result['master_files'])
  for file in os.listdir(dir):
    path = os.path.join(dir, file)
    if os.path.isfile(path):
      data = toJSON(path)
      if data:
        if file in existing:
          url = 'https://api.getlocalization.com/%s/api/update-master/' % projectName
          existing.remove(file)
        else:
          url = 'https://api.getlocalization.com/%s/api/create-master/json/%s/' % (projectName, locale)

        content_type, body = encode_multipart_formdata(file, data.encode('utf-8'))
        request = urllib2.Request(url, body)
        request.add_header('Content-Type', content_type)
        request.add_header('Content-Length', len(body))
        opener.open(request).read()

  for file in existing:
    print 'Warning: master file %s needs to be removed' % file
