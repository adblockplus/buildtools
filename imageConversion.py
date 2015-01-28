# coding: utf-8

# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

import os
import re

try:
  from PIL import Image
  from PIL import ImageOps
except ImportError:
  import Image
  import ImageOps

from imageCompression import image_to_file

def get_alpha(image):
  if image.mode in ('RGBA', 'LA'):
    return image.split()[image.getbands().index('A')]

  # In order to generate an alpha channel for images using a palette, we
  # convert the image to RGBA. It's important to use RGBA, not LA (grayscale+alpha),
  # since PIL can't reliably convert P to LA. Also initially, we created an
  # alpha channel by replacing opaque pixels with a high mark and transparent
  # pixels with a low mark. However, it turned out that you can't rely on the
  # value of Image.info['transparency'] since in some cases it might be an
  # unparsed string instead an int indicating the value of transparent pixels.
  if image.mode == 'P' and 'transparency' in image.info:
    return image.convert('RGBA').split()[3]

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

def filter_contrastToAlpha(image, baseDir):
  alpha = Image.new('L', image.size, 255)
  alpha.paste(image, mask=get_alpha(image))
  alpha = ImageOps.invert(alpha)
  alpha = ImageOps.autocontrast(alpha)

  return Image.merge('LA', [Image.new('L', image.size), alpha])

def filter_blend(image, baseDir, filename, opacity):
  image, overlay = ensure_same_mode(
    image,
    load_image(os.path.join(
      baseDir,
      *filename.split('/')
    ))
  )

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

    file = image_to_file(image, filename)
    try:
      files[filename] = file.read()
    finally:
      file.close()
