/* This Source Code Form is subject to the terms of the Mozilla Public
 * License, v. 2.0. If a copy of the MPL was not distributed with this
 * file, You can obtain one at http://mozilla.org/MPL/2.0/. */

function hook(obj, name, func, cleanup)
{
  let orig = obj[name];
  let origGet = obj.__lookupGetter__(name);
  let origSet = obj.__lookupSetter__(name);
  let dumbOverrideAttempt = false;

  let newFunc = function()
  {
    let params = arguments;
    try
    {
      let result = func.apply(this, params);
      if (typeof result == "object")
        params = result;
    }
    catch(e)
    {
      Cu.reportError(e);
    }

    try
    {
      return orig.apply(this, params);
    }
    finally
    {
      if (typeof cleanup == "function")
        cleanup();
    }
  };
  newFunc.toString = function()
  {
    dumbOverrideAttempt = true;
    return orig.toString();
  };
  newFunc.toSource = function()
  {
    dumbOverrideAttempt = true;
    return orig.toSource();
  }

  obj.__defineGetter__(name, function()
  {
    dumbOverrideAttempt = false;
    return newFunc;
  });

  obj.__defineSetter__(name, function(value)
  {
    if (dumbOverrideAttempt)
    {
      orig = value;
    }
    else
    {
      delete obj[name];
      obj[name] = value;
    }
  });

  return function()
  {
    delete obj[name];
    obj[name] = orig;
    if (origGet)
    {
      obj.__defineGetter__(name, origGet);
    }
    if (origSet)
    {
      obj.__defineSetter__(name, origSet);
    }
  };
}
exports.hook = hook;
