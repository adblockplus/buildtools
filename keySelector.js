/*
 * This Source Code is subject to the terms of the Mozilla Public License
 * version 2.0 (the "License"). You can obtain a copy of the License at
 * http://mozilla.org/MPL/2.0/.
 */

const Cc = Components.classes;
const Ci = Components.interfaces;
const Cu = Components.utils;

Cu.import("resource://gre/modules/Services.jsm");

/**
 * Translation table for key modifier names.
 */
let validModifiers =
{
  ACCEL: "control",
  CTRL: "control",
  CONTROL: "control",
  SHIFT: "shift",
  ALT: "alt",
  META: "meta",
  __proto__: null
};

let existingShortcuts = null;

/**
 * Sets the correct value of validModifiers.ACCEL.
 */
function initAccelKey()
{
  try
  {
    let accelKey = Services.prefs.getIntPref("ui.key.accelKey");
    if (accelKey == Ci.nsIDOMKeyEvent.DOM_VK_CONTROL)
      validModifiers.ACCEL = "control";
    else if (accelKey == Ci.nsIDOMKeyEvent.DOM_VK_ALT)
      validModifiers.ACCEL = "alt";
    else if (accelKey == Ci.nsIDOMKeyEvent.DOM_VK_META)
      validModifiers.ACCEL = "meta";
  }
  catch(e)
  {
    Cu.reportError(e);
  }
}

/**
 * Finds out which keyboard shortcuts are already taken in an application window,
 * converts them to canonical form in the existingShortcuts variable.
 */
function initExistingShortcuts(/**ChromeWindow*/ window)
{
  existingShortcuts = {__proto__: null};

  let keys = window.document.getElementsByTagName("key");
  for (let i = 0; i < keys.length; i++)
  {
    let key = keys[i];
    let keyData =
    {
      shift: false,
      meta: false,
      alt: false,
      control: false,
      char: null,
      code: null
    };

    let keyChar = key.getAttribute("key");
    if (keyChar && keyChar.length == 1)
      keyData.char = keyChar.toUpperCase();

    let keyCode = key.getAttribute("keycode");
    if (keyCode && "DOM_" + keyCode.toUpperCase() in Ci.nsIDOMKeyEvent)
      keyData.code = Ci.nsIDOMKeyEvent["DOM_" + keyCode.toUpperCase()];

    if (!keyData.char && !keyData.code)
      continue;

    let keyModifiers = key.getAttribute("modifiers");
    if (keyModifiers)
      for each (let modifier in keyModifiers.toUpperCase().match(/\w+/g))
        if (modifier in validModifiers)
          keyData[validModifiers[modifier]] = true;

    let canonical = [keyData.shift, keyData.meta, keyData.alt, keyData.control, keyData.char || keyData.code].join(" ");
    existingShortcuts[canonical] = true;
  }
}

/**
 * Creates the text representation for a key.
 */
function getTextForKey(/**Object*/ keyData) /**String*/
{
  try
  {
    let stringBundle = Services.strings.createBundle("chrome://global-platform/locale/platformKeys.properties");
    let parts = [];
    if (keyData.control)
      parts.push(stringBundle.GetStringFromName("VK_CONTROL"));
    if (keyData.alt)
      parts.push(stringBundle.GetStringFromName("VK_ALT"));
    if (keyData.meta)
      parts.push(stringBundle.GetStringFromName("VK_META"));
    if (keyData.shift)
      parts.push(stringBundle.GetStringFromName("VK_SHIFT"));
    if (keyData.char)
      parts.push(keyData.char.toUpperCase());
    else
    {
      let stringBundle2 = Services.strings.createBundle("chrome://global/locale/keys.properties");
      parts.push(stringBundle2.GetStringFromName(keyData.codeName));
    }
    return parts.join(stringBundle.GetStringFromName("MODIFIER_SEPARATOR"));
  }
  catch (e)
  {
    Cu.reportError(e);
    return null;
  }
}

exports.selectKey = selectKey;

/**
 * Selects a keyboard shortcut variant that isn't already taken in the window,
 * parses it into an object.
 */
function selectKey(/**ChromeWindow*/ window, /**String*/ variants) /**Object*/
{
  if (!existingShortcuts)
  {
    initAccelKey();
    initExistingShortcuts(window);
  }

  for each (let variant in variants.split(/\s*,\s*/))
  {
    if (!variant)
      continue;

    let keyData =
    {
      shift: false,
      meta: false,
      alt: false,
      control: false,
      char: null,
      code: null,
      codeName: null,
      text: null
    };
    for each (let part in variant.toUpperCase().split(/\s+/))
    {
      if (part in validModifiers)
        keyData[validModifiers[part]] = true;
      else if (part.length == 1)
        keyData.char = part;
      else if ("DOM_VK_" + part in Ci.nsIDOMKeyEvent)
      {
        keyData.code = Ci.nsIDOMKeyEvent["DOM_VK_" + part];
        keyData.codeName = "VK_" + part;
      }
    }

    if (!keyData.char && !keyData.code)
      continue;

    let canonical = [keyData.shift, keyData.meta, keyData.alt, keyData.control, keyData.char || keyData.code].join(" ");
    if (canonical in existingShortcuts)
      continue;

    keyData.text = getTextForKey(keyData);
    return keyData;
  }

  return null;
}
