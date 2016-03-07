/* This Source Code Form is subject to the terms of the Mozilla Public
 * License, v. 2.0. If a copy of the MPL was not distributed with this
 * file, You can obtain one at http://mozilla.org/MPL/2.0/. */

let {Services} = Cu.import("resource://gre/modules/Services.jsm", {});
let {XPCOMUtils} = Cu.import("resource://gre/modules/XPCOMUtils.jsm", {});

let {addonRoot, addonName} = require("info");
let branchName = "extensions." + addonName + ".";
let branch = Services.prefs.getBranch(branchName);
let preconfiguredBranch =
    Services.prefs.getBranch(branchName + "preconfigured.");
let ignorePrefChanges = false;

function init()
{
  // Load default preferences and set up properties for them
  let defaultBranch = Services.prefs.getDefaultBranch(branchName);

  let prefsData = require("prefs.json");
  let defaults = prefsData.defaults;
  let preconfigurable = new Set(prefsData.preconfigurable);
  for (let pref in defaults)
  {
    let value = defaults[pref];
    let [getter, setter] = typeMap[typeof value];
    if (preconfigurable.has(pref))
    {
      try
      {
        value = getter(preconfiguredBranch, pref);
      }
      catch (e) {}
    }
    setter(defaultBranch, pref, value);
    defineProperty(pref, false, getter, setter);
  }

  // Add preference change observer
  try
  {
    branch.QueryInterface(Ci.nsIPrefBranch2).addObserver("", Prefs, true);
    onShutdown.add(() => branch.removeObserver("", Prefs));
  }
  catch (e)
  {
    Cu.reportError(e);
  }
}

/**
 * Sets up getter/setter on Prefs object for preference.
 */
function defineProperty(/**String*/ name, defaultValue, /**Function*/ readFunc, /**Function*/ writeFunc)
{
  let value = defaultValue;
  Prefs["_update_" + name] = () =>
  {
    try
    {
      value = readFunc(branch, name);
      triggerListeners(name);
    }
    catch(e)
    {
      Cu.reportError(e);
    }
  };
  Object.defineProperty(Prefs, name, {
    enumerable: true,
    get: () => value,
    set: (newValue) =>
    {
      if (value == newValue)
        return value;

      try
      {
        ignorePrefChanges = true;
        writeFunc(branch, name, newValue);
        value = newValue;
        Services.prefs.savePrefFile(null);
        triggerListeners(name);
      }
      catch(e)
      {
        Cu.reportError(e);
      }
      finally
      {
        ignorePrefChanges = false;
      }
      return value;
    }
  });
  Prefs["_update_" + name]();
}

let listeners = [];
function triggerListeners(/**String*/ name)
{
  for (let i = 0; i < listeners.length; i++)
  {
    try
    {
      listeners[i](name);
    }
    catch(e)
    {
      Cu.reportError(e);
    }
  }
}

/**
 * Manages the preferences for an extension, object properties corresponding
 * to extension's preferences are added automatically. Setting the property
 * will automatically change the preference, external preference changes are
 * also recognized automatically.
 */
let Prefs = exports.Prefs =
{
  /**
   * Migrates an old preference to a new name.
   */
  migrate: function(/**String*/ oldName, /**String*/ newName)
  {
    if (newName in this && Services.prefs.prefHasUserValue(oldName))
    {
      let [getter, setter] = typeMap[typeof this[newName]];
      try
      {
        this[newName] = getter(Services.prefs, oldName);
      } catch(e) {}
      Services.prefs.clearUserPref(oldName);
    }
  },

  /**
   * Adds a preferences listener that will be fired whenever a preference
   * changes.
   */
  addListener: function(/**Function*/ listener)
  {
    if (listeners.indexOf(listener) < 0)
      listeners.push(listener);
  },

  /**
   * Removes a preferences listener.
   */
  removeListener: function(/**Function*/ listener)
  {
    let index = listeners.indexOf(listener);
    if (index >= 0)
      listeners.splice(index, 1);
  },

  observe: function(subject, topic, data)
  {
    if (ignorePrefChanges || topic != "nsPref:changed")
      return;

    if ("_update_" + data in this)
      this["_update_" + data]();
  },

  QueryInterface: XPCOMUtils.generateQI([Ci.nsISupportsWeakReference, Ci.nsIObserver])
};

let getIntPref = (branch, pref) => branch.getIntPref(pref);
let setIntPref = (branch, pref, newValue) => branch.setIntPref(pref, newValue);

let getBoolPref = (branch, pref) => branch.getBoolPref(pref);
let setBoolPref = (branch, pref, newValue) => branch.setBoolPref(pref, newValue);

let getCharPref = (branch, pref) => branch.getComplexValue(pref, Ci.nsISupportsString).data;
let setCharPref = (branch, pref, newValue) =>
{
  let str = Cc["@mozilla.org/supports-string;1"].createInstance(Ci.nsISupportsString);
  str.data = newValue;
  branch.setComplexValue(pref, Ci.nsISupportsString, str);
};

let getJSONPref = (branch, pref) => JSON.parse(getCharPref(branch, pref));
let setJSONPref = (branch, pref, newValue) => setCharPref(branch, pref, JSON.stringify(newValue));

// Getter/setter functions for difference preference types
let typeMap =
{
  boolean: [getBoolPref, setBoolPref],
  number: [getIntPref, setIntPref],
  string: [getCharPref, setCharPref],
  object: [getJSONPref, setJSONPref]
};

init();
