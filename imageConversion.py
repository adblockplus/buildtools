# coding: utf-8

# This file is part of the Adblock Plus build tools,
# Copyright (C) 2006-2013 Eyeo GmbH
#
# Adblock Plus is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 3 as
# published by the Free Software Foundation.
#
# Adblock Plus is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with Adblock Plus.  If not, see <http://www.gnu.org/licenses/>.

import os
import re
from StringIO import StringIO

try:
  from PIL import Image
  from PIL import ImageOps
except ImportError:
  import Image
  import ImageOps

def get_alpha(image):
  if image.mode in ('RGBA', 'LA'):
    return image.split()[image.getbands().index('A')]

  if image.mode == 'P':
    transparency = image.info.get('transparency')

    if transparency is not None:
      table = [255] * 256
      table[transparency] = 0

      return image.point(table, 'L')

def load_image(path):
  image = Image.open(path)
  # Make sure the image is loaded, some versions of PIL load images lazily.
  image.load()
  return image

def ensure_same_mode(im1, im2):
  # if both images already have the same mode (and palette, in
  # case of mode P), don't convert anything. Images with mode P,
  # and a different palette, are the only case where images
  # using the same mode, will be incompatible with each other.
  if im1.mode == im2.mode and (im1.mode != 'P' or im1.getpalette() == im2.getpalette()):
    return (im1, im2)

  # if any given image has a mode that supports colors convert both
  # images to RGB or RGBA, otherwise convert both images to L or LA.
  # If any given image has an alpha channel (or mode P which
  # can store transparent pixels too) convert both images
  # to RGBA or LA, otherwise convert both images to RGB or L.
  mode = max(
    Image.getmodebase(im1.mode),
    Image.getmodebase(im2.mode),

    key=('L', 'RGB').index
  )

  if any(im.mode in ('RGBA', 'LA', 'P') for im in (im1, im2)):
    mode += 'A'

  return (
    im1 if im1.mode == mode else im1.convert(mode),
    im2 if im2.mode == mode else im2.convert(mode),
  )

def filter_grayscale(image, baseDir):
  alpha = get_alpha(image)
  image = image.convert('L')

  if alpha:
    image.putalpha(alpha)

  return image

def filter_contrastToAlpha(image, baseDir):
  alpha = Image.new('L', image.size, 255)
  alpha.paste(image, mask=get_alpha(image))
  alpha = ImageOps.invert(alpha)
  alpha = ImageOps.autocontrast(alpha)

  return Image.merge('LA', [Image.new('L', image.size), alpha])

def filter_blend(image, baseDir, *args):
  if len(args) == 2:
    filename, opacity = args

    overlay = load_image(os.path.join(
      baseDir,
      *filename.split('/')
    ))
  else:
    red, green, blue, opacity = args

    overlay = Image.new('RGB', image.size, (
      int(red),
      int(green),
      int(blue),
    ))

    # if the background image has an alpha channel copy it to
    # the overlay, so that transparent areas stay transparent.
    alpha = get_alpha(image)
    if alpha:
      overlay.putalpha(alpha)

  image, overlay = ensure_same_mode(image, overlay)
  return Image.blend(image, overlay, float(opacity))

def convertImages(params, files):
  metadata = params['metadata']

  for filename, chain in metadata.items('convert_img'):
    baseDir = os.path.dirname(metadata.option_source('convert_img', filename))
    steps = re.split(r'\s*->\s*', chain)
    image = load_image(os.path.join(baseDir, *steps.pop(0).split('/')))

    for step in steps:
      filter, args = re.match(r'([^(]+)(?:\((.*)\))?', step).groups()
      args = re.split(r'\s*,\s*', args) if args else ()
      image = globals()['filter_' + filter](image, baseDir, *args)

    f = StringIO()
    f.name = filename
    image.save(f)
    files[filename] = f.getvalue()
