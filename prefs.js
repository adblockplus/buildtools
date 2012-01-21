/*
 * This Source Code is subject to the terms of the Mozilla Public License
 * version 2.0 (the "License"). You can obtain a copy of the License at
 * http://mozilla.org/MPL/2.0/.
 */

const Cc = Components.classes;
const Ci = Components.interfaces;
const Cu = Components.utils;

Cu.import("resource://gre/modules/Services.jsm");
Cu.import("resource://gre/modules/XPCOMUtils.jsm");

let {addonRoot} = require("info");

let Prefs = exports.Prefs =
{
  branch: null,
  ignorePrefChanges: false,

  init: function(branchName, migrate)
  {
    if (this.branch)
      return;
    this.branch = Services.prefs.getBranch(branchName);

    /**
     * Sets up getter/setter on Prefs object for preference.
     */
    function defineProperty(/**String*/ name, defaultValue, /**Function*/ readFunc, /**Function*/ writeFunc)
    {
      let value = defaultValue;
      this["_update_" + name] = function()
      {
        try
        {
          value = readFunc(this.branch, name);
        }
        catch(e)
        {
          Cu.reportError(e);
        }
      };
      Prefs.__defineGetter__(name, function() value);
      Prefs.__defineSetter__(name, function(newValue)
      {
        if (value == newValue)
          return value;

        try
        {
          this.ignorePrefChanges = true;
          writeFunc(this.branch, name, newValue);
          value = newValue;
        }
        catch(e)
        {
          Cu.reportError(e);
        }
        finally
        {
          this.ignorePrefChanges = false;
        }
        return value;
      });
      this["_update_" + name]();
    }

    // Load default preferences and set up properties for them
    let defaultBranch = Services.prefs.getDefaultBranch(branchName);
    let typeMap =
    {
      boolean: [getBoolPref, setBoolPref],
      number: [getIntPref, setIntPref],
      string: [getCharPref, setCharPref],
      object: [getJSONPref, setJSONPref]
    };
    let scope =
    {
      pref: function(pref, value)
      {
        if (pref.substr(0, branchName.length) != branchName)
        {
          Cu.reportError(new Error("Ignoring default preference " + pref + ", wrong branch."));
          return;
        }
        pref = pref.substr(branchName.length);

        let [getter, setter] = typeMap[typeof value];
        setter(defaultBranch, pref, value);
        defineProperty.call(Prefs, pref, false, getter, setter);
      }
    };
    Services.scriptloader.loadSubScript(addonRoot + "defaults/preferences/prefs.js", scope);

    // Add preference change observer
    try
    {
      this.branch.QueryInterface(Ci.nsIPrefBranch2)
                 .addObserver("", this, true);
    }
    catch (e)
    {
      Cu.reportError(e);
    }

    // Migrate preferences stored under outdated names
    if (migrate)
    {
      for (let oldName in migrate)
      {
        let newName = migrate[oldName];
        if (newName in this && Services.prefs.prefHasUserValue(oldName))
        {
          let [getter, setter] = typeMap[typeof this[newName]];
          try
          {
            this[newName] = getter(Services.prefs, oldName);
          } catch(e) {}
          Services.prefs.clearUserPref(oldName);
        }
      }
    }
  },

  shutdown: function()
  {
    if (!this.branch)
      return;

    try
    {
      this.branch.QueryInterface(Ci.nsIPrefBranch2)
                 .removeObserver("", this);
    }
    catch (e)
    {
      Cu.reportError(e);
    }
    this.branch = null;
  },

  observe: function(subject, topic, data)
  {
    if (this.ignorePrefChanges || topic != "nsPref:changed")
      return;

    if ("_update_" + data in this)
      this["_update_" + data]();
  },

  QueryInterface: XPCOMUtils.generateQI([Ci.nsISupportsWeakReference, Ci.nsIObserver])
};

function getIntPref(branch, pref) branch.getIntPref(pref)
function setIntPref(branch, pref, newValue) branch.setIntPref(pref, newValue)

function getBoolPref(branch, pref) branch.getBoolPref(pref)
function setBoolPref(branch, pref, newValue) branch.setBoolPref(pref, newValue)

function getCharPref(branch, pref) branch.getComplexValue(pref, Ci.nsISupportsString).data
function setCharPref(branch, pref, newValue)
{
  let str = Cc["@mozilla.org/supports-string;1"].createInstance(Ci.nsISupportsString);
  str.data = newValue;
  branch.setComplexValue(pref, Ci.nsISupportsString, str);
}

function getJSONPref(branch, pref) JSON.parse(getCharPref(branch, pref))
function setJSONPref(branch, pref, newValue) setCharPref(branch, pref, JSON.stringify(newValue))
